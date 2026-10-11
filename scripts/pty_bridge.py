#!/usr/bin/env python3
"""Transport terminal bytes separately from control messages. No translation here."""

import errno
import fcntl
import json
import os
import pty
import selectors
import signal
import struct
import sys
import termios
import time


def emit(message):
    try:
        os.write(3, (json.dumps(message) + '\n').encode())
    except OSError:
        pass


def dimensions(fd, cols, rows):
    cols, rows = max(1, min(int(cols), 10000)), max(1, min(int(rows), 10000))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))


def main():
    if len(sys.argv) < 2:
        raise ValueError('Missing executable')
    master, slave = pty.openpty()
    dimensions(slave, os.environ.get('CODEX_ZH_COLS', 120), os.environ.get('CODEX_ZH_ROWS', 36))
    pid = os.fork()
    if pid == 0:
        try:
            os.close(master)
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            for target in (0, 1, 2):
                os.dup2(slave, target)
            if slave > 2:
                os.close(slave)
            os.close(3)
            os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
        except BaseException as error:
            os.write(2, ('PTY: ' + str(error) + '\n').encode())
            os._exit(127)
    os.close(slave)
    os.set_blocking(master, False)
    selector = selectors.DefaultSelector()
    selector.register(master, selectors.EVENT_READ, 'terminal')
    selector.register(0, selectors.EVENT_READ, 'input')
    selector.register(3, selectors.EVENT_READ, 'control')
    controls = b''
    pending = bytearray()
    status = None
    shutdown_at = None
    drain_until = None

    def kill_child(sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass

    try:
        while status is None or any(key.data == 'terminal' for key in selector.get_map().values()):
            for key, events in selector.select(0.05):
                if key.data == 'terminal':
                    if events & selectors.EVENT_WRITE:
                        try:
                            written = os.write(master, pending)
                            del pending[:written]
                        except BlockingIOError:
                            pass
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            pending.clear()
                        if not pending and master in selector.get_map():
                            selector.modify(master, selectors.EVENT_READ, 'terminal')
                    if events & selectors.EVENT_READ:
                        try:
                            data = os.read(master, 65536)
                        except OSError as error:
                            if error.errno not in (errno.EIO, errno.EAGAIN):
                                raise
                            data = b'' if error.errno == errno.EIO else None
                        if data:
                            view = memoryview(data)
                            while view:
                                written = os.write(1, view)
                                view = view[written:]
                        elif data == b'':
                            selector.unregister(master)
                else:
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fd)
                        kill_child(signal.SIGHUP)
                        shutdown_at = time.monotonic() + 1
                        continue
                    if key.data == 'input':
                        pending.extend(data)
                        if master in selector.get_map():
                            selector.modify(master, selectors.EVENT_READ | selectors.EVENT_WRITE, 'terminal')
                    else:
                        controls += data
                        if len(controls) > 65536:
                            raise ValueError('Oversized PTY control message')
                        while b'\n' in controls:
                            line, controls = controls.split(b'\n', 1)
                            message = json.loads(line)
                            if message.get('op') == 'resize':
                                dimensions(master, message['cols'], message['rows'])
                            elif message.get('op') == 'signal':
                                allowed = {'SIGINT', 'SIGTERM', 'SIGHUP', 'SIGKILL'}
                                if message.get('signal') in allowed:
                                    kill_child(getattr(signal, message['signal']))
            if status is None:
                finished, observed = os.waitpid(pid, os.WNOHANG)
                if finished:
                    status = observed
                    drain_until = time.monotonic() + 0.25
            if drain_until is not None and time.monotonic() >= drain_until:
                break
            if shutdown_at is not None and time.monotonic() >= shutdown_at:
                kill_child(signal.SIGKILL)
                shutdown_at = None
        emit({'event': 'exit', 'exitCode': os.WEXITSTATUS(status) if os.WIFEXITED(status) else 0,
              'signal': os.WTERMSIG(status) if os.WIFSIGNALED(status) else 0})
    finally:
        selector.close()
        os.close(master)
        if status is None:
            kill_child(signal.SIGHUP)
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                finished, _ = os.waitpid(pid, os.WNOHANG)
                if finished:
                    break
                time.sleep(0.01)
            else:
                kill_child(signal.SIGKILL)
                os.waitpid(pid, 0)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        emit({'event': 'error', 'message': str(error)})
        sys.exit(1)
