#!/usr/bin/env bash
set -euo pipefail
python3 /opt/codex-zh-test/scripts/container_guard.py
TEST_WORK_DIR="$(mktemp -d /tmp/codex-zh-container.XXXXXX)"
trap 'rm -rf -- "$TEST_WORK_DIR"' EXIT
cp -R /opt/codex-zh-test/. "$TEST_WORK_DIR/"
cd -- "$TEST_WORK_DIR"
node --version
python3 --version
node --test --test-concurrency=2
node scripts/validate-data.js
bash -n install.sh uninstall.sh scripts/container-entry.sh
python3 - <<'PY'
from pathlib import Path
for filename in Path('scripts').glob('*.py'):
    compile(filename.read_bytes(), str(filename), 'exec')
print('Python syntax checks passed.')
PY
python3 -m unittest discover -s scripts -p test_container_test.py
python3 scripts/smoke_frontend.py node
python3 scripts/container_install_check.py
printf '%s\n' 'CONTAINER_TEST_PASSED: isolation, unit tests, full PTY and install/uninstall.'
