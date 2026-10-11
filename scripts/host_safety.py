#!/usr/bin/env python3
"""Back up selected settings privately, then compare without automatic restoration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Authentication is hashed only; credentials are never copied into the backup.
CONFIG_FILES = ('.zshrc', '.zprofile', '.bash_profile', '.bashrc', '.profile',
                '.ssh/config', '.codex/config.toml')
HASH_ONLY_FILES = ('.codex/auth.json',)
RUNTIME_PATHS = ('.lima', '.colima', '.docker', '.orbstack', '.local/share/containers',
                 'Library/Caches/lima')
OFFICIAL_ENTRY = Path('/opt/homebrew/bin/codex')


def describe(path):
    if not os.path.lexists(path):
        return {'exists': False}
    info = path.lstat()
    result = {'exists': True, 'mode': stat.S_IMODE(info.st_mode)}
    if path.is_symlink():
        result['link_target'] = os.readlink(path)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        result['sha256'] = digest.hexdigest()
    elif path.is_dir():
        result['directory'] = True
    return result


def snapshot():
    parent = ROOT / 'test-results' / 'host-safety'
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    destination = Path(tempfile.mkdtemp(prefix='before-', dir=parent))
    home = Path.home()
    records = {}
    for name in CONFIG_FILES + HASH_ONLY_FILES + RUNTIME_PATHS:
        path = home / name
        records[name] = describe(path)
        if name in CONFIG_FILES and path.is_file():
            backup = destination / 'settings' / name
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            for directory in [backup.parent, *backup.parent.parents]:
                if directory == destination.parent:
                    break
                os.chmod(directory, 0o700)
            with backup.open('xb') as handle:
                os.chmod(backup, 0o600)
                handle.write(path.read_bytes())
    records['official_codex_entry'] = describe(OFFICIAL_ENTRY)
    report = {'created_at': datetime.now(timezone.utc).isoformat(),
              'authentication_copied': False, 'records': records}
    manifest = destination / 'snapshot.json'
    manifest.write_text(json.dumps(report, indent=2) + '\n')
    os.chmod(manifest, 0o600)
    print(str(destination))


def compare(destination):
    destination = destination.resolve()
    allowed = (ROOT / 'test-results' / 'host-safety').resolve()
    if not destination.is_relative_to(allowed):
        raise ValueError('Use a snapshot directory within this project.')
    report = json.loads((destination / 'snapshot.json').read_text())
    differences = []
    for name, previous in report['records'].items():
        if name == 'official_codex_entry':
            path = OFFICIAL_ENTRY
        elif name in CONFIG_FILES + HASH_ONLY_FILES + RUNTIME_PATHS:
            path = Path.home() / name
        else:
            raise ValueError('Unknown snapshot record.')
        if describe(path) != previous:
            differences.append(name)
    result = {'passed': not differences, 'changed_paths': differences,
              'checked_at': datetime.now(timezone.utc).isoformat(),
              'restored_files': [], 'scope': 'selected settings, auth hash, official entry and runtime paths'}
    target = destination / 'comparison.json'
    target.write_text(json.dumps(result, indent=2) + '\n')
    os.chmod(target, 0o600)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not differences else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('snapshot')
    check = actions.add_parser('check')
    check.add_argument('directory', type=Path)
    args = parser.parse_args()
    if args.action == 'snapshot':
        snapshot()
        return 0
    return compare(args.directory)


if __name__ == '__main__':
    raise SystemExit(main())
