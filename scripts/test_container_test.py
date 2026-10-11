#!/usr/bin/env python3
"""Security-relevant tests for context filtering and container policy validation."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import uuid
from unittest.mock import patch

import container_test as runner


def configuration():
    return {'Config': {'User': '1000:1000', 'Volumes': None,
                       'Env': ['PATH=/usr/local/bin:/usr/bin:/bin', 'HTTP_PROXY=']},
            'Mounts': [], 'HostConfig': {
                'NetworkMode': 'none', 'ReadonlyRootfs': True, 'Privileged': False,
                'CapDrop': ['ALL'], 'CapAdd': None, 'SecurityOpt': ['no-new-privileges=true'],
                'Binds': None, 'Mounts': [], 'VolumesFrom': None,
                'Tmpfs': {'/tmp': 'rw,nosuid,nodev,exec,size=268435456,mode=1777'},
                'PidMode': '', 'IpcMode': 'private', 'PortBindings': {}, 'Devices': [],
                'Memory': 536870912, 'MemorySwap': 536870912, 'PidsLimit': 256,
                'NanoCpus': 2000000000}}


class ContainerRunnerTests(unittest.TestCase):
    def test_context_excludes_credentials_profiles_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = ('PRIVATE_SENTINEL_' + uuid.uuid4().hex).encode()
            for name in runner.FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                # These tests verify context boundaries using synthetic source.
                # Builder control files need not be present in the runtime image.
                target.write_text('Public source fixture: ' + name + '\n')
            for name in ['.codex/auth.json', '.ssh/id_ed25519', '.env', '.zshrc',
                         'data/private.json', 'scripts/private.py', 'bin/private.js']:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(sentinel)
            context, records = runner.make_context(root)
            self.assertFalse(sentinel in context, 'Unlisted private contents entered the context.')
            with tarfile.open(fileobj=io.BytesIO(context)) as archive:
                self.assertEqual(set(archive.getnames()), set(runner.FILES))
                self.assertTrue(all(item.isfile() and item.uid == item.gid == item.mtime == 0
                                    and item.uname == item.gname == '' for item in archive.getmembers()))
            self.assertEqual(len(records), len(runner.FILES))

    def test_context_rejects_symlink_file_and_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Dockerfile').symlink_to(runner.ROOT / 'Dockerfile')
            with self.assertRaisesRegex(ValueError, 'symlink'):
                runner.make_context(root)
            (root / 'Dockerfile').unlink()
            (root / 'lib').symlink_to(runner.ROOT / 'lib', target_is_directory=True)
            with patch.object(runner, 'FILES', ('lib/settings.js',)):
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    runner.make_context(root)

    def test_secure_configuration_and_tmpfs_inspect_variants(self):
        info = configuration()
        self.assertTrue(runner.check_configuration(info)['passed'])
        info['Mounts'] = [{'Type': 'tmpfs', 'Source': '', 'Destination': '/tmp'}]
        self.assertTrue(runner.check_configuration(info)['passed'])

    def test_configuration_rejects_mount_network_privilege_and_environment_leaks(self):
        unsafe = [
            ('HostConfig', 'NetworkMode', 'host'), ('HostConfig', 'ReadonlyRootfs', False),
            ('HostConfig', 'Privileged', True), ('HostConfig', 'CapAdd', ['SYS_ADMIN']),
            ('HostConfig', 'CapDrop', []), ('HostConfig', 'SecurityOpt', []),
            ('HostConfig', 'Binds', ['/Users/alvin:/host']),
            ('HostConfig', 'VolumesFrom', ['unrelated']), ('HostConfig', 'PidMode', 'host'),
            ('HostConfig', 'IpcMode', 'host'), ('HostConfig', 'Memory', 0),
            ('Config', 'User', '0:0'), ('Config', 'Volumes', {'/host': {}}),
            ('Config', 'Env', ['OPENAI_API_KEY=PRIVATE_SENTINEL']),
            ('Config', 'Env', ['HTTP_PROXY=http://private-proxy']),
        ]
        for section, key, value in unsafe:
            with self.subTest(key=key):
                info = configuration()
                info[section][key] = value
                with self.assertRaises(RuntimeError):
                    runner.check_configuration(info)
        info = configuration()
        info['Mounts'] = [{'Type': 'bind', 'Source': '/Users/alvin', 'Destination': '/tmp'}]
        with self.assertRaises(RuntimeError):
            runner.check_configuration(info)

    def test_rejected_policy_removes_only_created_container_without_starting_it(self):
        calls = []
        container_id = 'a' * 64
        info = configuration()
        info['HostConfig']['Binds'] = ['/Users/alvin:/host']

        def fake_call(engine, arguments, **kwargs):
            calls.append(arguments)
            text = ''
            if arguments[0] == 'info':
                text = 'linux\n'
            elif arguments[:2] == ['image', 'inspect']:
                text = 'sha256:' + 'b' * 64 + '\n'
            elif arguments[0] == 'create':
                text = container_id + '\n'
            elif arguments[0] == 'inspect':
                text = json.dumps([info])
            return subprocess.CompletedProcess(arguments, 0, text, '')

        with (tempfile.TemporaryDirectory() as directory,
              patch.object(runner, 'engine_call', fake_call),
              patch.object(runner, 'build_image')):
            with self.assertRaises(RuntimeError):
                runner.run_tests('fixture-docker', b'context', Path(directory))
        self.assertFalse(any(args[0] == 'start' for args in calls))
        self.assertEqual(calls[-1], ['rm', '--force', container_id])
        self.assertFalse(any('prune' in args for args in calls))

    def test_failed_build_preserves_output_and_source_input(self):
        script = ('import sys; data=sys.stdin.buffer.read(); '
                  'print("fixture build error", file=sys.stderr); '
                  'sys.exit(7 if data==b"fixture-context" else 8)')
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            destination = Path(directory)
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner.build_image(sys.executable, ['-c', script], b'fixture-context', destination)
            self.assertEqual(raised.exception.returncode, 7)
            self.assertIn(b'fixture build error', (destination / 'build.log').read_bytes())


if __name__ == '__main__':
    unittest.main()
