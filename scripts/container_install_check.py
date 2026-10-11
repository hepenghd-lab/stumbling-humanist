#!/usr/bin/env python3
"""Exercise the actual shell installers using only synthetic temporary data."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='codex-container-install-') as directory:
        fixture = Path(directory)
        bin_dir = fixture / 'bin'
        bin_dir.mkdir()
        official = bin_dir / 'codex'
        official.write_text('#!/bin/sh\nprintf "%s\\n" "fixture official CLI"\n')
        official.chmod(0o755)
        config_dir = fixture / 'official-config'
        config_dir.mkdir()
        config = config_dir / 'config.toml'
        config.write_text('[desktop]\nlocaleOverride = "en"\n# synthetic fixture\n')
        auth = config_dir / 'auth.json'
        auth.write_text('{"fixture_only": true, "token": "NOT-A-REAL-SECRET"}\n')
        profile = fixture / '.zshrc'
        profile.write_text('# synthetic shell profile\n')
        protected = [official, config, auth, profile]
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
        environment = {**os.environ, 'CODEX_ZH_BIN_DIR': str(bin_dir), 'CODEX_HOME': str(config_dir)}
        subprocess.run(['bash', str(source / 'install.sh')], cwd=source, env=environment, check=True)
        for name in ['codex-zh-local', 'codex-zh-local-doctor']:
            assert (bin_dir / name).is_symlink(), name
        result = subprocess.run([str(bin_dir / 'codex-zh-local'), '--codex-bin', str(official), '--version'],
                                cwd=source, env=environment, check=True, capture_output=True)
        assert result.stdout == b'fixture official CLI\n' and result.stderr == b''
        subprocess.run(['bash', str(source / 'uninstall.sh')], cwd=source, env=environment, check=True)
        for name in ['codex-zh-local', 'codex-zh-local-doctor']:
            assert not os.path.lexists(bin_dir / name), name
        assert before == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in protected}
        assert not (source / '.local-install-state.json').exists()
        print('Shell install/uninstall passed; synthetic CLI/config/auth/profile hashes unchanged.')


if __name__ == '__main__':
    main()
