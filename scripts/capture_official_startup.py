#!/usr/bin/env python3
"""Record real CLI startup with a temporary HOME and an invalid local-only provider."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import tempfile
import termios
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--node', type=Path, help='Use current wrapper when supplied; otherwise direct CLI')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    official = args.codex.resolve(strict=True)
    source = Path(__file__).resolve().parents[1]
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codex-ui-isolated-') as directory:
        root = Path(directory)
        config, work = root / 'config', root / 'work'
        config.mkdir(); work.mkdir()
        (config / 'config.toml').write_text(
            'model = "gpt-5"\nmodel_provider = "fixture"\n'
            '[model_providers.fixture]\nname = "Isolated UI fixture"\n'
            'base_url = "http://127.0.0.1:9/v1"\n'
            'env_key = "CODEX_UI_FIXTURE_KEY"\nwire_api = "responses"\n'
            '[projects."' + str(work) + '"]\ntrust_level = "trusted"\n')
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(root), 'CODEX_HOME': str(config),
               'CODEX_ZH_HOME': str(root / 'wrapper-settings'), 'TERM': 'xterm-256color',
               'LANG': 'en_US.UTF-8', 'CODEX_UI_FIXTURE_KEY': 'NOT-A-REAL-KEY'}
        command = [str(official), '--disable', 'shell_snapshot']
        if args.node:
            command = [str(args.node.resolve(strict=True)), str(source / 'bin/codex-zh.js'),
                       '--codex-bin', str(official), '--codex-zh-lang', 'zh',
                       '--disable', 'shell_snapshot']
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(work)
            os.execve(command[0], command, env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 120, 0, 0))
        data, tail = bytearray(), b''
        deadline, quitting = time.monotonic() + 12, False
        queries = (
            (b'\x1b[6n', b'\x1b[1;1R'), (b'\x1b[c', b'\x1b[?1;2c'),
            (b'\x1b[?u', b'\x1b[?0u'),
            (b'\x1b]11;?\x07', b'\x1b]11;rgb:1111/1111/1111\x07'),
            (b'\x1b]11;?\x1b\\', b'\x1b]11;rgb:1111/1111/1111\x1b\\'),
        )
        status = None
        try:
            while time.monotonic() < deadline:
                if select.select([fd], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    data.extend(chunk); tail += chunk
                    for query, answer in queries:
                        if query in tail:
                            os.write(fd, answer); tail = tail.replace(query, b'')
                    tail = tail[-100:]
                if not quitting and time.monotonic() > deadline - 2:
                    try:
                        os.write(fd, b'\x03\x03')
                    except OSError:
                        break
                    quitting = True
        finally:
            os.close(fd)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            cleanup_deadline = time.monotonic() + 3
            while time.monotonic() < cleanup_deadline:
                ended, status = os.waitpid(pid, os.WNOHANG)
                if ended:
                    break
                time.sleep(0.05)
            else:
                os.kill(pid, signal.SIGKILL)
                _, status = os.waitpid(pid, 0)
        text = data.decode('utf8').replace(str(root), '/tmp/codex-ui-fixture')
        text = re.sub(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',
                      '00000000-0000-0000-0000-000000000000', text)
        name = 'wrapper-startup' if args.node else 'official-startup'
        (args.output / (name + '.ansi')).write_text(text)
        report = {
            'real_official_binary': True, 'wrapper_enabled': bool(args.node),
            'official_binary_sha256': hashlib.sha256(official.read_bytes()).hexdigest(),
            'temporary_home_and_config': True, 'provider': 'invalid local-only endpoint',
            'real_account_supplied': False, 'user_tasks_submitted': 0,
            'output_bytes_before_redaction': len(data),
            'output_cjk_characters': len(re.findall(r'[\u4e00-\u9fff]', text)),
            'unicode_decode_succeeded': True,
            'exit_status': os.waitstatus_to_exitcode(status),
            'capture_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'temporary_settings_removed': False,
        }
    report['temporary_settings_removed'] = not root.exists()
    (args.output / (name + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    if args.node and not report['output_cjk_characters']:
        raise SystemExit('Real wrapper startup produced no Chinese output.')


if __name__ == '__main__':
    main()
