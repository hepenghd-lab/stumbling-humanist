#!/usr/bin/env python3
"""Verify published evidence bytes, exact tested source and recorded pass markers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'verification/2026-10-11-arm64'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(evidence, root, require_current=False):
    sums = evidence / 'SHA256SUMS'
    expected_files = set()
    for line in sums.read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts, 'Unsafe checksum path')
        require(path.name == name and name not in expected_files, 'Duplicate/non-flat evidence path')
        expected_files.add(name)
        file = evidence / name
        require(file.is_file() and not file.is_symlink(), 'Missing/nonregular evidence: ' + name)
        require(hashlib.sha256(file.read_bytes()).hexdigest() == digest, 'Hash mismatch: ' + name)
    actual_files = {p.name for p in evidence.iterdir() if p.name != 'SHA256SUMS'}
    require(actual_files == expected_files, 'Unlisted or missing evidence files')
    load = lambda name: json.loads((evidence / name).read_text())
    result = load('result.json')
    overall = load('temporary-runtime-result.json')
    require(result.get('passed') is True and result.get('exit_code') == 0
            and result.get('oom_killed') is False, 'Container did not pass')
    for key in ('passed', 'container_tests_passed', 'runtime_removed', 'settings_unchanged'):
        require(overall.get(key) is True, 'Overall failure: ' + key)
    require(not overall.get('errors') and overall.get('retained_runtime') is None, 'Cleanup/errors remain')
    host = load('host-comparison.json')
    require(host.get('passed') is True and not host.get('changed_paths'), 'Host comparison failed')
    isolation = load('isolation.json')
    require(isolation.get('passed') is True and isolation.get('host_mounts') == []
            and isolation.get('network') == 'none' and isolation.get('user') == '1000:1000'
            and isolation.get('readonly_root') is True
            and isolation.get('memory_bytes') == 536870912 and isolation.get('pids_limit') == 256,
            'Unexpected published isolation policy')
    vm = load('vm-isolation.json')
    require(vm.get('passed') is True and vm.get('mounts') == []
            and vm.get('port_forwards') == [] and vm.get('ssh_agent_forwarded') is False,
            'Unexpected published VM isolation')
    log = (evidence / 'container.log').read_text()
    for marker in ('tests 58', 'pass 58', 'fail 0', 'skipped 0', 'Ran 6 tests',
                   'Validated 49 entries, 24 approved groups',
                   'Full frontend PTY smoke passed', 'Shell install/uninstall passed',
                   'CONTAINER_TEST_PASSED'):
        require(marker in log, 'Missing actual-run marker: ' + marker)
    manifest = load('context-manifest.json')
    records = manifest['files']
    require(len(records) == 42 and len({r['path'] for r in records}) == 42, 'Expected 42 unique source files')
    context = evidence / 'source-context.tar'
    require(hashlib.sha256(context.read_bytes()).hexdigest() == manifest['context_sha256'],
            'Context archive hash mismatch')
    expected = {r['path']: r for r in records}
    changed_source = []
    with tarfile.open(context, 'r:') as archive:
        members = archive.getmembers()
        require(len(members) == 42 and {m.name for m in members} == set(expected), 'Context members differ')
        for member in members:
            rel = Path(member.name)
            require(member.isfile() and not rel.is_absolute() and '..' not in rel.parts, 'Unsafe member')
            require(member.uid == 0 and member.gid == 0 and member.mtime == 0, 'Host metadata in archive')
            record = expected[member.name]
            content = archive.extractfile(member).read()
            require(len(content) == record['size']
                    and hashlib.sha256(content).hexdigest() == record['sha256'], 'Archived source changed')
            live = root / rel
            cursor = root
            for component in rel.parts:
                cursor = cursor / component
                require(not cursor.is_symlink(), 'Current source symlink: ' + member.name)
            if not live.is_file() or hashlib.sha256(live.read_bytes()).hexdigest() != record['sha256']:
                changed_source.append(member.name)
    if require_current:
        require(not changed_source, 'Current source differs from historical run: ' + ', '.join(changed_source))
    # Credentials/config snapshots are never part of this flat evidence bundle.
    for name in expected_files:
        if name.endswith(('.json', '.log', '.md')):
            text = (evidence / name).read_text()
            require(not re.search(r'/Users/(?!REDACTED(?:/|\b))[^\s/]+', text),
                    'Personal home path in evidence: ' + name)
            require('BEGIN PRIVATE KEY' not in text, 'Private key marker in evidence')
    return {'passed': True, 'tested_source_files': 42, 'node_tests': 58,
            'python_container_tests': 6, 'entries': 49, 'groups': 24,
            'matches_current_source': not changed_source, 'changed_source_files': changed_source,
            'tested_version': '1.2.1-local.1',
            'scope': 'internal consistency and recorded results; not an independent rerun'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=DEFAULT)
    parser.add_argument('--require-current-source', action='store_true',
                        help='Fail if current source differs from the historical tested snapshot')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.evidence.resolve(), ROOT, args.require_current_source), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, tarfile.TarError) as error:
        raise SystemExit('Evidence verification failed: ' + str(error))


if __name__ == '__main__':
    main()
