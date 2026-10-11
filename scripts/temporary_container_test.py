#!/usr/bin/env python3
"""Temporary Lima VM -> isolated Docker tests -> remove VM/runtime -> check settings."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile

from container_test import run_logged

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.2.1'
LIMA_URL = 'https://github.com/lima-vm/lima/releases/download/v2.2.1/lima-2.2.1-Darwin-arm64.tar.gz'
LIMA_SHA256 = '9e9eacce88f37e185c346bad73aa6136f738d8cdf8c3bb23cd42b071824bc66e'
IMAGE_URL = 'https://cloud-images.ubuntu.com/releases/noble/release-20260926/ubuntu-24.04-server-cloudimg-arm64.img'
IMAGE_SHA256 = '1d6bffe64b848468ac97f821d369a4846d983de1800ccf6b5ec8853e85cefc55'
INSTANCE = 'cztest'
MARKER = '.codex-zh-owned-runtime'
RUNTIME_PARENT = Path('/private/tmp')
VM_INSTALL_SCRIPT = '''set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# Skip optional translations/AppStream metadata; keep package signature checks.
apt-get -o Acquire::Languages=none -o Acquire::IndexTargets::deb::DEP-11::DefaultEnabled=false -o Acquire::IndexTargets::deb::CNF::DefaultEnabled=false update
apt-get install -y --no-install-recommends docker.io python3
systemctl enable --now docker
docker info --format '{{.OSType}}'
'''


def call(arguments, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('timeout', 60)
    if 'input' not in kwargs:
        kwargs.setdefault('stdin', subprocess.DEVNULL)
    return subprocess.run([str(item) for item in arguments], **kwargs)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def download(url, checksum, destination):
    print('下载并校验：' + url, flush=True)
    call(['/usr/bin/curl', '--fail', '--location', '--proto', '=https',
          '--proto-redir', '=https', '--connect-timeout', '15', '--max-time', '1200',
          '--output', destination, url], timeout=1210)
    if digest(destination) != checksum:
        destination.unlink()
        raise RuntimeError('SHA-256 不匹配；文件已删除，不执行下载内容。')


def extract_runtime(archive_path, destination):
    """Never extract devices, hardlinks, escaping paths or files through symlinks."""
    with tarfile.open(archive_path, 'r:gz') as archive:
        links = []
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('Unsafe archive path.')
            target = destination.joinpath(*name.parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Archive path escapes runtime.')
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError('Missing archive member.')
                with source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
            elif member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or not (target.parent / str(link)).resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Archive link escapes runtime.')
                links.append((target, member.linkname))
            else:
                raise ValueError('Unsupported archive member type.')
        for target, link in links:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if target.exists() or target.is_symlink():
                raise ValueError('Duplicate archive member.')
            target.symlink_to(link)
        for target, _ in links:
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Archive link chain escapes runtime.')


def vm_configuration(image):
    # JSON is a YAML subset. No upstream docker template/get.docker.com script.
    return {'minimumLimaVersion': VERSION, 'vmType': 'vz', 'arch': 'aarch64',
            'cpus': 2, 'memory': '2GiB', 'disk': '12GiB', 'plain': True,
            'images': [{'location': str(image), 'arch': 'aarch64', 'digest': 'sha256:' + IMAGE_SHA256}],
            'mounts': [], 'portForwards': [],
            'ssh': {'loadDotSSHPubKeys': False, 'forwardAgent': False,
                    'forwardX11': False, 'forwardX11Trusted': False},
            # Slow package downloads run after Lima reports READY, because its
            # hostagent readiness check has an independent ~10 minute limit.
            'containerd': {'system': False, 'user': False}}


def remove_owned_runtime(runtime):
    runtime = Path(runtime)
    if (runtime.is_symlink() or not runtime.name.startswith('czrt-')
            or runtime.parent.resolve() != RUNTIME_PARENT.resolve()
            or not (runtime / MARKER).is_file()
            or (runtime / MARKER).read_text() != 'codex-zh-local temporary test\n'):
        raise RuntimeError('拒绝删除不属于本次测试的运行目录。')
    shutil.rmtree(runtime)


def main():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64' or os.geteuid() == 0:
        raise RuntimeError('本脚本需要 Apple Silicon macOS 普通用户；不使用宿主机 sudo。')
    if shutil.disk_usage(RUNTIME_PARENT).free < 8 * 1024 ** 3:
        raise RuntimeError('临时虚拟机需要至少 8 GiB 可用空间。')
    snapshot_result = call([sys.executable, ROOT / 'scripts/host_safety.py', 'snapshot'],
                           capture_output=True, text=True)
    snapshot = Path(snapshot_result.stdout.strip())
    print('已私密备份配置：' + str(snapshot), flush=True)
    reports = ROOT / 'test-results' / 'container'
    reports.mkdir(parents=True, exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix='czrt-', dir=RUNTIME_PARENT))
    (runtime / MARKER).write_text('codex-zh-local temporary test\n')
    (reports / 'temporary-runtime-result.json').write_text(json.dumps(
        {'passed': None, 'status': 'running', 'backup': str(snapshot),
         'active_runtime': str(runtime)}, indent=2) + '\n')
    environment = {'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                   'LIMA_HOME': str(runtime / 'l'), 'SSH': '/usr/bin/ssh',
                   'LIMA_TEMPLATES_PATH': str(runtime / 'prefix/share/lima/templates')}
    limactl = runtime / 'prefix/bin/limactl'
    vm_attempted, cleanup_ok, test_passed = False, False, False
    errors = []
    try:
        archive = runtime / 'lima.tar.gz'
        download(LIMA_URL, LIMA_SHA256, archive)
        prefix = runtime / 'prefix'
        prefix.mkdir(mode=0o700)
        extract_runtime(archive, prefix)
        call([limactl, '--version'], env=environment)
        image = runtime / 'ubuntu-arm64.img'
        download(IMAGE_URL, IMAGE_SHA256, image)
        configuration = runtime / 'vm.yaml'
        configuration.write_text(json.dumps(vm_configuration(image), indent=2) + '\n')
        call([limactl, 'validate', configuration], env=environment)
        vm_attempted = True
        run_logged(str(limactl), ['--tty=false', 'start', '--name=' + INSTANCE, '--mount-none',
              '--plain', '--vm-type=vz', '--timeout=15m', configuration],
             b'', reports, env=environment, timeout=960, log_name='vm-start.log')
        # Inspect the effective VM settings before transmitting any project file.
        effective = call([limactl, 'list', '--json', INSTANCE], env=environment,
                         capture_output=True, text=True)
        vm = json.loads(effective.stdout.strip())
        applied = vm['config']
        if applied.get('mounts') or applied.get('portForwards') or not applied.get('plain'):
            raise RuntimeError('虚拟机包含共享目录或端口转发，停止测试。')
        ssh = applied.get('ssh', {})
        if ssh.get('forwardAgent') or ssh.get('loadDotSSHPubKeys'):
            raise RuntimeError('虚拟机 SSH 隔离不符合要求，停止测试。')
        (reports / 'vm-isolation.json').write_text(json.dumps({'passed': True, 'mounts': [],
            'port_forwards': [], 'ssh_agent_forwarded': False, 'vm_type': 'vz'}, indent=2) + '\n')
        print('虚拟机启动与隔离检查通过；现在单独安装 Docker（最多等待 30 分钟）。', flush=True)
        run_logged(str(limactl), ['--tty=false', 'shell', '--preserve-env=false',
                   '--workdir=/tmp', INSTANCE, 'sudo', '-n', 'bash', '-c', VM_INSTALL_SCRIPT],
                   b'', reports, env=environment, timeout=1800, log_name='vm-install.log')
        # The adapter executes Docker inside the VM; no host Docker client/config.
        adapter = runtime / 'docker-test'
        adapter.write_text('#!/bin/sh\nexec ' + shlex.quote(str(limactl)) +
            ' --tty=false shell --preserve-env=false --workdir=/tmp ' + INSTANCE + ' sudo -n docker "$@"\n')
        adapter.chmod(0o700)
        call([sys.executable, ROOT / 'scripts/container_test.py', '--engine', adapter],
             env=environment, timeout=900)
        test_passed = json.loads((reports / 'result.json').read_text()).get('passed') is True
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        errors.append(str(error))
        print('临时测试停止：' + str(error), file=sys.stderr, flush=True)
    finally:
        # SIGINT/TERM must not interrupt the cleanup itself. SIGKILL/power loss
        # cannot be handled; retain a runtime path in the report for recovery.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        cleanup_ok = not vm_attempted
        if vm_attempted:
            try:
                call([limactl, '--tty=false', 'stop', '--force', INSTANCE], env=environment, timeout=90)
                call([limactl, '--tty=false', 'delete', '--force', INSTANCE], env=environment, timeout=90)
                cleanup_ok = True
            except (OSError, subprocess.SubprocessError) as error:
                errors.append('VM cleanup failed: ' + str(error))
        if cleanup_ok:
            try:
                remove_owned_runtime(runtime)
            except (OSError, RuntimeError) as error:
                cleanup_ok = False
                errors.append(str(error))
        checked = call([sys.executable, ROOT / 'scripts/host_safety.py', 'check', snapshot],
                       capture_output=True, text=True, check=False)
        settings_unchanged = checked.returncode == 0
        if not settings_unchanged:
            errors.append('所检查的设置发生变化；保留备份，不自动覆盖并发修改。')
        report = {'passed': test_passed and cleanup_ok and settings_unchanged,
                  'status': 'passed' if test_passed and cleanup_ok and settings_unchanged else 'failed',
                  'container_tests_passed': test_passed, 'runtime_removed': cleanup_ok,
                  'settings_unchanged': settings_unchanged, 'backup': str(snapshot),
                  'retained_runtime': None if cleanup_ok else str(runtime), 'errors': errors}
        (reports / 'temporary-runtime-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    def stop_requested(signum, frame):
        raise KeyboardInterrupt('Stop requested; cleaning up temporary environment.')
    signal.signal(signal.SIGTERM, stop_requested)
    raise SystemExit(main())
