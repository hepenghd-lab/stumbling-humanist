#!/bin/bash
set -euo pipefail
TEST_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec /usr/bin/python3 "$TEST_SOURCE_DIR/scripts/temporary_container_test.py"
