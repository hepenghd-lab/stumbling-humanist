#!/usr/bin/env python3
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import temporary_container_test as temporary


class TemporaryRuntimeTests(unittest.TestCase):
    def test_vm_config_has_no_home_mounts_agent_forwarding_or_remote_shell_installer(self):
        config = temporary.vm_configuration(Path('/private/tmp/fixture/ubuntu.img'))
        self.assertTrue(config['plain'])
        self.assertEqual(config['mounts'], [])
        self.assertEqual(config['portForwards'], [])
        self.assertFalse(any(config['ssh'].values()))
        self.assertFalse(any(config['containerd'].values()))
        self.assertFalse(config.get('provision'))
        self.assertNotIn('curl', temporary.VM_INSTALL_SCRIPT)
        self.assertIn('docker.io', temporary.VM_INSTALL_SCRIPT)
        self.assertEqual(config['images'][0]['digest'], 'sha256:' + temporary.IMAGE_SHA256)

    def test_download_rejects_wrong_checksum_and_deletes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'fixture.tar.gz'

            def fake_download(arguments, **kwargs):
                target.write_bytes(b'wrong fixture bytes')
                return subprocess.CompletedProcess(arguments, 0)

            with patch.object(temporary, 'call', fake_download), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                    temporary.download('https://example.invalid/fixture', '0' * 64, target)
            self.assertFalse(target.exists())

    def test_archive_allows_internal_links_but_rejects_escape_and_special_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, kind, link, valid in [
                ('bin/limactl', tarfile.REGTYPE, '', True),
                ('bin/lima', tarfile.SYMTYPE, 'limactl', True),
                ('../outside', tarfile.REGTYPE, '', False),
                ('/absolute', tarfile.REGTYPE, '', False),
                ('bin/escape', tarfile.SYMTYPE, '../../outside', False),
                ('device', tarfile.CHRTYPE, '', False),
            ]:
                with self.subTest(name=name):
                    output = root / 'output'
                    output.mkdir(exist_ok=True)
                    archive = root / 'fixture.tar.gz'
                    with tarfile.open(archive, 'w:gz') as pack:
                        item = tarfile.TarInfo(name)
                        item.type = kind
                        item.linkname = link
                        pack.addfile(item, io.BytesIO(b''))
                    if valid:
                        temporary.extract_runtime(archive, output)
                        self.assertTrue((output / name).exists())
                    else:
                        with self.assertRaises(ValueError):
                            temporary.extract_runtime(archive, output)
                    self.assertFalse((root / 'outside').exists())

    def test_failed_download_cleans_only_owned_runtime_and_still_checks_settings(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / 'snapshot-fixture'
            backup.mkdir()

            def fake_call(arguments, **kwargs):
                calls.append([str(item) for item in arguments])
                if 'snapshot' in arguments:
                    return subprocess.CompletedProcess(arguments, 0, str(backup) + '\n', '')
                return subprocess.CompletedProcess(arguments, 0, '{}', '')

            with (patch.object(temporary, 'ROOT', root),
                  patch.object(temporary, 'RUNTIME_PARENT', root),
                  patch.object(temporary, 'call', fake_call),
                  patch.object(temporary, 'download', side_effect=RuntimeError('fixture download failed')),
                  patch.object(temporary.platform, 'system', return_value='Darwin'),
                  patch.object(temporary.platform, 'machine', return_value='arm64'),
                  patch.object(temporary.os, 'geteuid', return_value=501),
                  patch.object(temporary.shutil, 'disk_usage', return_value=SimpleNamespace(free=16 * 1024 ** 3)),
                  patch.object(temporary.signal, 'signal'),
                  contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                self.assertEqual(temporary.main(), 1)
            report = json.loads((root / 'test-results/container/temporary-runtime-result.json').read_text())
            self.assertTrue(report['runtime_removed'])
            self.assertTrue(report['settings_unchanged'])
            self.assertFalse(report['container_tests_passed'])
            self.assertIsNone(report['retained_runtime'])
            self.assertTrue(backup.exists())
            self.assertTrue(any('check' in args for args in calls))
            self.assertFalse(any('start' in args or 'delete' in args for args in calls))
            with self.assertRaises(RuntimeError):
                temporary.remove_owned_runtime(backup)

    def test_install_failure_after_vm_ready_preserves_logs_and_cleans_vm(self):
        calls, stages = [], []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup = root / 'snapshot-fixture'
            backup.mkdir()

            def fake_call(arguments, **kwargs):
                arguments = [str(item) for item in arguments]
                calls.append(arguments)
                if 'snapshot' in arguments:
                    return subprocess.CompletedProcess(arguments, 0, str(backup) + '\n', '')
                if 'list' in arguments:
                    config = {'plain': True, 'mounts': [], 'portForwards': [], 'ssh': {}}
                    return subprocess.CompletedProcess(arguments, 0, json.dumps({'config': config}), '')
                return subprocess.CompletedProcess(arguments, 0, '{}', '')

            def fake_logged(engine, arguments, context, destination, **kwargs):
                stages.append((arguments, kwargs))
                (destination / kwargs['log_name']).write_text('fixture stage output\n')
                if 'shell' in arguments:
                    self.assertTrue((destination / 'vm-isolation.json').exists())
                    raise subprocess.CalledProcessError(9, [engine, *arguments])

            with (patch.object(temporary, 'ROOT', root),
                  patch.object(temporary, 'RUNTIME_PARENT', root),
                  patch.object(temporary, 'call', fake_call),
                  patch.object(temporary, 'run_logged', fake_logged),
                  patch.object(temporary, 'download'),
                  patch.object(temporary, 'extract_runtime'),
                  patch.object(temporary.platform, 'system', return_value='Darwin'),
                  patch.object(temporary.platform, 'machine', return_value='arm64'),
                  patch.object(temporary.os, 'geteuid', return_value=501),
                  patch.object(temporary.shutil, 'disk_usage', return_value=SimpleNamespace(free=16 * 1024 ** 3)),
                  patch.object(temporary.signal, 'signal'),
                  contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO())):
                self.assertEqual(temporary.main(), 1)
            self.assertIn('start', stages[0][0])
            self.assertIn('shell', stages[1][0])
            self.assertEqual(stages[1][1]['timeout'], 1800)
            self.assertEqual(stages[1][1]['log_name'], 'vm-install.log')
            self.assertTrue(any('stop' in args for args in calls))
            self.assertTrue(any('delete' in args for args in calls))
            report = json.loads((root / 'test-results/container/temporary-runtime-result.json').read_text())
            self.assertTrue(report['runtime_removed'])
            self.assertFalse(report['container_tests_passed'])
            self.assertTrue((root / 'test-results/container/vm-install.log').exists())


if __name__ == '__main__':
    unittest.main()
