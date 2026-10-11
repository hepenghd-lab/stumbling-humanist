#!/usr/bin/env python3
"""Exercise the full wrapper inside a real outer TTY, using an isolated fake CLI."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import selectors
import struct
import subprocess
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
NODE = sys.argv[1] if len(sys.argv) > 1 else 'node'
FIXTURE = '''#!/usr/bin/env python3
import os,sys,tty
tty.setraw(0)
sys.stdout.write("\\x1b[1mExplored\\x1b[0m\\n")
sys.stdout.write("\\x1b[1mRan\\x1b[0m python test.py\\n")
sys.stdout.write("Failed (exit 7)\\n")
sys.stdout.write("{\\"status\\":\\"Working\\"}\\n")
sys.stdout.write("print(\\"Working\\")\\n")
sys.stdout.write("› 1. Yes, proceed (y)\\n")
sys.stdout.write("37% context left\\nREADY\\n")
sys.stdout.flush()
data=b''
while not data.endswith(b'\\n'):
 data+=os.read(0,1024)
sys.stdout.write('ECHO '+data.decode('utf8'))
sys.stdout.flush()
sys.exit(17)
'''


def main():
    with tempfile.TemporaryDirectory(prefix='codex-local-smoke-') as directory:
        fixture = Path(directory) / 'codex-fixture'
        fixture.write_text(FIXTURE)
        fixture.chmod(0o755)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
        proc = subprocess.Popen([NODE, str(ROOT / 'bin/codex-zh.js'), '--codex-bin', str(fixture),
                                 '--codex-zh-lang', 'zh'], stdin=slave, stdout=slave, stderr=slave,
                                cwd=ROOT, start_new_session=True,
                                env={**os.environ, 'CODEX_ZH_SKIP': '0', 'TERM': 'xterm-256color'})
        os.close(slave)
        selector = selectors.DefaultSelector()
        selector.register(master, selectors.EVENT_READ)
        output, sent = bytearray(), False
        deadline = time.monotonic() + 5
        try:
            while time.monotonic() < deadline:
                for _, _ in selector.select(0.05):
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b''
                    if not chunk:
                        selector.unregister(master)
                        break
                    output.extend(chunk)
                    if not sent and b'READY' in output:
                        sent = True
                        text = '你好\n'.encode()
                        os.write(master, text[:1])
                        time.sleep(0.01)
                        os.write(master, text[1:])
                if not selector.get_map():
                    break
            code = proc.wait(timeout=1)
        finally:
            selector.close()
            os.close(master)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        text = output.decode('utf8')
        visible = re.sub(r'\x1b\[[0-9;:]*m', '', text).replace('\r', '')
        expected = ['已探查', '运行python test.py', '失败（退出码7）', '{"status":"Working"}',
                    'print("Working")', '› 1. 是，继续 (y)', '剩余上下文 37%', 'ECHO 你好']
        for item in expected:
            assert item in visible, (item, visible)
        assert '�' not in visible
        assert code == 17, (code, visible)
        report = {'passed': True, 'fixture_only': True, 'exit_code': code,
                  'checks': expected, 'visible_output': visible}
        destination = ROOT / 'test-results'
        destination.mkdir(exist_ok=True)
        (destination / 'interactive-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print('Full frontend PTY smoke passed: Chinese labels/input, protected code/JSON, option keys, exit 17.')


if __name__ == '__main__':
    main()
