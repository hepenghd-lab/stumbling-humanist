#!/usr/bin/env python3
"""Build an allowlisted context and run tests without any host filesystem mounts."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import select
import signal
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'codex-zh-local-test:1.2.1-local.1'
LABEL = 'codex-zh-local.purpose=isolated-test'
# Exact names, not directory globs: unrelated files can never enter the context.
FILES = (
    'Dockerfile', '.dockerignore', 'LICENSE', 'package.json', 'package-lock.json',
    'install.sh', 'uninstall.sh',
    'bin/codex-zh.js', 'bin/codex-zh-doctor.js',
    'data/ui-translations-local.json',
    'lib/ansi-tokenizer.js', 'lib/config-overlay.js', 'lib/detect.js',
    'lib/language-toggle.js', 'lib/matcher.js', 'lib/pty-bridge.js',
    'lib/run-mode.js', 'lib/settings.js', 'lib/translator.js',
    'lib/ui-matcher.js', 'lib/width.js',
    'scripts/container-entry.sh', 'scripts/container_guard.py',
    'scripts/container_install_check.py', 'scripts/container_test.py',
    'scripts/test_container_test.py', 'scripts/manage-links.js',
    'scripts/pty_bridge.py', 'scripts/smoke_frontend.py', 'scripts/validate-data.js',
    'tests/ansi-tokenizer.test.js', 'tests/cli.test.js',
    'tests/config-overlay.test.js', 'tests/detect.test.js',
    'tests/language-toggle.test.js', 'tests/manage-links.test.js',
    'tests/matcher.test.js', 'tests/pty-bridge.test.js',
    'tests/run-mode.test.js', 'tests/settings.test.js',
    'tests/translator.test.js', 'tests/width.test.js',
)


def make_context(root=ROOT):
    root = root.resolve()
    output = io.BytesIO()
    records = []
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in FILES:
            path = root / name
            # Reject links at every component, including links to files inside root.
            cursor = root
            for part in Path(name).parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise ValueError('Context symlink rejected: ' + name)
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or not path.resolve().is_relative_to(root):
                raise ValueError('Context must contain only local regular files: ' + name)
            content = path.read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755 if mode & 0o111 else 0o644
            # Fixed metadata avoids copying host usernames, ownership or timestamps.
            archive.addfile(info, io.BytesIO(content))
            records.append({'path': name, 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    return output.getvalue(), records


def create_arguments(image=IMAGE):
    return ['create', '--label', LABEL, '--network=none', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges=true',
            '--user=1000:1000', '--pids-limit=256', '--memory=512m',
            '--memory-swap=512m', '--cpus=2',
            '--tmpfs=/tmp:rw,nosuid,nodev,exec,size=268435456,mode=1777',
            # Override Docker client's optional automatic proxy environment.
            '--env=HTTP_PROXY=', '--env=HTTPS_PROXY=', '--env=ALL_PROXY=',
            '--env=NO_PROXY=', '--env=http_proxy=', '--env=https_proxy=',
            '--env=all_proxy=', '--env=no_proxy=', image]


def check_configuration(info):
    def require(condition, message='Resource limits do not match the test policy.'):
        if not condition:
            raise RuntimeError(message)

    host = info['HostConfig']
    require(info['Config']['User'] == '1000:1000', 'Unexpected container user.')
    require(host['NetworkMode'] == 'none', 'Networking is not disabled.')
    require(host['ReadonlyRootfs'] and not host['Privileged'], 'Filesystem/privilege policy changed.')
    require({item.upper() for item in host['CapDrop']} >= {'ALL'}, 'Capabilities not dropped.')
    require(not host.get('CapAdd'), 'Added capabilities are forbidden.')
    require(any(item in ('no-new-privileges', 'no-new-privileges=true')
                for item in host['SecurityOpt']), 'Privilege escalation protection missing.')
    require(not host.get('Binds') and not host.get('Mounts'), 'Host/volume mounts are forbidden.')
    require(not host.get('VolumesFrom'), 'Inherited volumes are forbidden.')
    require(host.get('Tmpfs', {}).keys() == {'/tmp'}, 'Only /tmp may be a temporary mount.')
    require(not info['Config'].get('Volumes'), 'Image-declared volumes are forbidden.')
    for mount in info.get('Mounts') or []:
        require(mount['Type'] == 'tmpfs' and mount['Destination'] == '/tmp' and not mount.get('Source'), 'Unexpected mounted storage.')
    require(host.get('PidMode') != 'host' and host.get('IpcMode') != 'host', 'Host namespaces forbidden.')
    require(not host.get('PortBindings') and not host.get('Devices'), 'Ports/devices are forbidden.')
    require(host['Memory'] == 512 * 1024 * 1024 and host['MemorySwap'] == host['Memory'])
    require(host['PidsLimit'] == 256 and host['NanoCpus'] == 2_000_000_000)
    allowed_environment = {'PATH', 'NODE_VERSION', 'YARN_VERSION', 'PYTHONDONTWRITEBYTECODE', 'CODEX_ZH_HOME', 'TERM'}
    for item in info['Config'].get('Env') or []:
        name, value = item.split('=', 1)
        if name.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}:
            require(value == '', 'Host proxy values must not enter the container.')
        else:
            require(name in allowed_environment, 'Unexpected container environment: ' + name)
    return {'passed': True, 'host_mounts': [], 'network': 'none', 'user': '1000:1000',
            'readonly_root': True, 'memory_bytes': host['Memory'], 'pids_limit': host['PidsLimit']}


def engine_call(engine, arguments, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('timeout', 30)
    if 'input' not in kwargs:
        kwargs.setdefault('stdin', subprocess.DEVNULL)
    return subprocess.run([engine, *arguments], **kwargs)


def run_logged(engine, arguments, context, destination, timeout=600, env=None, log_name='build.log'):
    """Keep command output even on failure, while streaming progress to the terminal."""
    log_path = destination / log_name
    with tempfile.TemporaryFile() as source, log_path.open('wb') as log:
        source.write(context)
        source.seek(0)
        process = subprocess.Popen([engine, *arguments], stdin=source,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True, bufsize=0, env=env)
        deadline, drain_deadline = time.monotonic() + timeout, None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired([engine, *arguments], timeout)
                if select.select([process.stdout], [], [], min(0.2, remaining))[0]:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    log.write(chunk)
                    log.flush()
                    if hasattr(sys.stdout, 'buffer'):
                        sys.stdout.buffer.write(chunk)
                    else:
                        sys.stdout.write(chunk.decode('utf8', errors='replace'))
                    sys.stdout.flush()
                if process.poll() is not None:
                    if drain_deadline is None:
                        drain_deadline = time.monotonic() + 1
                    if time.monotonic() >= drain_deadline:
                        break
            status = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            raise
        finally:
            process.stdout.close()
        if status:
            raise subprocess.CalledProcessError(status, [engine, *arguments])


def build_image(engine, arguments, context, destination, timeout=600):
    return run_logged(engine, arguments, context, destination, timeout=timeout)


def record_stage(destination, stage):
    (destination / 'result.json').write_text(json.dumps(
        {'passed': None, 'status': 'running', 'stage': stage}, indent=2) + '\n')


def run_tests(engine, context, destination, offline=False):
    record_stage(destination, 'checking_engine')
    kind = engine_call(engine, ['info', '--format', '{{.OSType}}'], capture_output=True, text=True).stdout.strip()
    if kind != 'linux':
        raise RuntimeError('The selected Docker daemon must run Linux containers.')
    # Build steps cannot use the host network namespace or any source/auth mounts.
    build = ['build', '--tag', IMAGE, '--label', LABEL, '--network=' + ('none' if offline else 'default'), '-']
    record_stage(destination, 'building_image')
    build_image(engine, build, context, destination)
    record_stage(destination, 'checking_image')
    image_id = engine_call(engine, ['image', 'inspect', '--format', '{{.Id}}', IMAGE],
                           capture_output=True, text=True).stdout.strip()
    container_id = engine_call(engine, create_arguments(image_id), capture_output=True, text=True).stdout.strip()
    if not container_id or not all(char in '0123456789abcdef' for char in container_id) or len(container_id) != 64:
        raise RuntimeError('Docker returned an invalid container ID; no unrelated resources will be removed.')
    try:
        record_stage(destination, 'checking_container_policy')
        info = json.loads(engine_call(engine, ['inspect', container_id], capture_output=True, text=True).stdout)[0]
        policy = check_configuration(info)
        (destination / 'isolation.json').write_text(json.dumps(policy, indent=2) + '\n')
        # No host environment is passed to the test process; only image ENV applies.
        record_stage(destination, 'running_container_tests')
        result = engine_call(engine, ['start', '--attach', container_id], capture_output=True, timeout=120, check=False)
        log = result.stdout + result.stderr
        (destination / 'container.log').write_bytes(log)
        sys.stdout.buffer.write(log)
        status = json.loads(engine_call(engine, ['inspect', container_id], capture_output=True, text=True).stdout)[0]['State']
        passed = result.returncode == 0 and status['ExitCode'] == 0 and b'CONTAINER_TEST_PASSED:' in log and not status.get('OOMKilled')
        report = {'passed': passed, 'status': 'passed' if passed else 'failed', 'image_id': image_id, 'container_id': container_id,
                  'exit_code': status['ExitCode'], 'oom_killed': status.get('OOMKilled', False)}
        (destination / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        if not passed:
            raise RuntimeError('Container tests failed; see test-results/container/container.log.')
    finally:
        # Remove only the container just created, never prune any images/volumes.
        engine_call(engine, ['rm', '--force', container_id], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true', help='Create the source-only context; do not contact Docker.')
    parser.add_argument('--engine', default='docker', help='Path to a trusted Docker-compatible CLI.')
    parser.add_argument('--offline', action='store_true', help='Disable build-step networking; base image/packages must be cached.')
    args = parser.parse_args()
    context, records = make_context()
    destination = ROOT / 'test-results' / 'container'
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'context.tar').write_bytes(context)
    manifest = {'context_sha256': hashlib.sha256(context).hexdigest(), 'files': records,
                'excludes': ['host home', 'Codex auth/config', 'shell profiles', 'unlisted project files']}
    (destination / 'context-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'result.json').write_text(json.dumps({'passed': None, 'status': 'prepared_only'}, indent=2) + '\n')
    print('Prepared exact source context: %d files, %d bytes.' % (len(records), len(context)), flush=True)
    if args.prepare:
        print('Preparation only. No container has been built or run.')
        return 0
    engine = shutil.which(args.engine)
    if not engine:
        print('缺少容器运行环境；测试包已生成，但未创建或运行容器。未安装软件或修改系统设置。', file=sys.stderr)
        return 2
    try:
        run_tests(engine, context, destination, args.offline)
    except (OSError, ValueError, AssertionError, RuntimeError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        report = json.loads((destination / 'result.json').read_text())
        report.update({'passed': False, 'status': 'failed', 'error': str(error)})
        (destination / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        raise
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, AssertionError, RuntimeError, subprocess.SubprocessError) as error:
        print('Container test stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
