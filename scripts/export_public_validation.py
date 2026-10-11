#!/usr/bin/env python3
"""Export selected completed-run evidence; never walk private host backups."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

JSON_FILES = (
    'context-manifest.json', 'isolation.json', 'result.json',
    'temporary-runtime-result.json', 'vm-isolation.json',
)
LOG_FILES = ('container.log', 'build.log', 'vm-start.log', 'vm-install.log')


def redact(text):
    text = re.sub(r'/Users/[^/\s\x60\"\x27]+', '/Users/REDACTED', text)
    text = re.sub(r'/private/tmp/czrt-[A-Za-z0-9_-]+', '/private/tmp/czrt-REDACTED', text)
    text = re.sub(r'before-[A-Za-z0-9_-]+', 'before-REDACTED', text)
    return re.sub(r'/tmp/codex-container-install-[A-Za-z0-9_-]+', '/tmp/fixture-install', text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Completed test-results/container directory')
    parser.add_argument('--comparison', type=Path, required=True, help='Only comparison.json; no snapshot files')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    overall = json.loads((source / 'temporary-runtime-result.json').read_text())
    if not all(overall.get(key) is True for key in (
            'passed', 'container_tests_passed', 'runtime_removed', 'settings_unchanged')):
        raise SystemExit('Refusing to export an incomplete or failed final run.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in JSON_FILES:
        path = source / name
        if path.is_symlink():
            raise SystemExit('Evidence symlink rejected: ' + name)
        data = json.loads(path.read_text())
        if name == 'temporary-runtime-result.json':
            data['backup'] = '[private backup omitted]'
        (output / name).write_text(redact(json.dumps(data, ensure_ascii=False, indent=2)) + '\n')
    for name in LOG_FILES:
        path = source / name
        if path.is_symlink():
            raise SystemExit('Evidence symlink rejected: ' + name)
        (output / name).write_text(redact(path.read_text()))
    comparison = json.loads(args.comparison.read_text())
    if comparison.get('passed') is not True or comparison.get('changed_paths'):
        raise SystemExit('Expected unchanged selected host paths.')
    # Explicit fields: do not copy snapshot metadata, paths, credentials or auth hashes.
    public_comparison = {key: comparison[key] for key in (
        'passed', 'changed_paths', 'checked_at', 'restored_files', 'scope')}
    (output / 'host-comparison.json').write_text(json.dumps(public_comparison, indent=2) + '\n')
    context = source / 'context.tar'
    if context.is_symlink():
        raise SystemExit('Context symlink rejected.')
    shutil.copyfile(context, output / 'source-context.tar')
    manifest = json.loads((output / 'context-manifest.json').read_text())
    if hashlib.sha256(context.read_bytes()).hexdigest() != manifest['context_sha256']:
        raise SystemExit('Original context hash mismatch.')
    print('Exported selected logs/JSON and exact source context. Private snapshots were not copied.')


if __name__ == '__main__':
    main()
