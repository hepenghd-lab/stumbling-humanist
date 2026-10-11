#!/usr/bin/env python3
"""Fail closed unless the test process has the required Linux isolation."""
import json
import os
from pathlib import Path


def check():
    def require(condition, message):
        if not condition:
            raise RuntimeError(message)

    require(os.uname().sysname == 'Linux', 'A Linux container is required.')
    require(os.getuid() == 1000 and os.getgid() == 1000, 'Use the unprivileged test user.')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    require(int(status['CapEff'].strip(), 16) == 0, 'Effective capabilities must be empty.')
    require(status['NoNewPrivs'].strip() == '1', 'no-new-privileges is required.')
    mounts = [line.split() for line in Path('/proc/mounts').read_text().splitlines()]
    root = next(row for row in mounts if row[1] == '/')
    temporary = next(row for row in mounts if row[1] == '/tmp')
    require('ro' in root[3].split(','), 'The root filesystem must be read-only.')
    require(temporary[2] == 'tmpfs', '/tmp must use memory-backed temporary storage.')
    require({'nosuid', 'nodev'}.issubset(temporary[3].split(',')), 'tmpfs mount protection missing.')
    require(set(os.listdir('/sys/class/net')) == {'lo'}, 'Networking must be disabled.')
    for forbidden in ['/var/run/docker.sock', '/run/podman/podman.sock', '/host', '/Users',
                      '/run/secrets', str(Path.home() / '.codex'), str(Path.home() / '.ssh')]:
        require(not Path(forbidden).exists(), 'Unexpected host/credential path: ' + forbidden)
    report = {'passed': True, 'uid': os.getuid(), 'network': 'loopback only',
              'root_filesystem': 'read-only', 'temporary_storage': 'tmpfs',
              'effective_capabilities': 0, 'no_new_privileges': True}
    print('Container isolation verified: ' + json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    check()
