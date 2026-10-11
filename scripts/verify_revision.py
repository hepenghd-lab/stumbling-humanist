#!/usr/bin/env python3
"""Check revision evidence, rerun public captures and match current container source."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'verification/1.2.1-local.2'


def main():
    expected = set()
    for line in (EVIDENCE / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        rel = Path(name)
        assert not rel.is_absolute() and '..' not in rel.parts and name not in expected
        expected.add(name)
        file = EVIDENCE / rel
        assert file.is_file() and not file.is_symlink()
        assert hashlib.sha256(file.read_bytes()).hexdigest() == digest, name
    actual = {p.relative_to(EVIDENCE).as_posix() for p in EVIDENCE.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    assert expected == actual, 'Evidence file set differs'
    manifest = json.loads((EVIDENCE / 'context-manifest.json').read_text())
    archive = EVIDENCE / 'source-context.tar'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['context_sha256']
    assert len(manifest['files']) == 47
    with tarfile.open(archive, 'r:') as tar:
        assert len(tar.getmembers()) == 47
        assert {x.name for x in tar.getmembers()} == {x['path'] for x in manifest['files']}
        for record in manifest['files']:
            rel = Path(record['path'])
            assert not rel.is_absolute() and '..' not in rel.parts
            member = tar.getmember(record['path'])
            assert member.isfile()
            content = tar.extractfile(member).read()
            assert hashlib.sha256(content).hexdigest() == record['sha256']
            assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == record['sha256'], record['path']
    load = lambda name: json.loads((EVIDENCE / name).read_text())
    before, after = load('before-replay.json'), load('after-replay.json')
    assert len(before['records']) == len(after['records']) == 8
    for old, new in zip(before['records'], after['records']):
        assert old['input_sha256'] == new['input_sha256']
        assert old['hits'] == old['cjk_characters'] == 0
        assert new['hits'] > 0 and new['cjk_characters'] > 0
        assert new['controls_unchanged'] and not new['invalid_utf8_output']
    node = sys.argv[1] if len(sys.argv) > 1 else 'node'
    rerun = json.loads(subprocess.check_output(
        [node, str(ROOT / 'scripts/replay_recordings.js'), str(EVIDENCE / 'recordings')]))
    assert rerun == after, 'Current replay differs from recorded results'
    live = load('live-wrapper-startup.json')
    assert live['real_official_binary'] and live['wrapper_enabled']
    assert live['output_cjk_characters'] > 0 and live['exit_status'] == 0
    assert live['user_tasks_submitted'] == 0 and not live['real_account_supplied']
    assert live['temporary_settings_removed']
    assert hashlib.sha256((EVIDENCE / 'live-wrapper-startup.ansi').read_bytes()).hexdigest() == live['capture_sha256']
    print(json.dumps({'passed': True, 'version': '1.2.1-local.2', 'source_files': 47,
                      'recordings_rerun': 8, 'control_sequences_unchanged': True,
                      'real_cli_startup_cjk': live['output_cjk_characters'],
                      'scope': 'source/evidence consistency plus offline rerun; not a new live model task'}, indent=2))


if __name__ == '__main__':
    main()
