#!/usr/bin/env bash
# Remove only launchers recorded by this local fork; retain source and settings.
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ "$#" -gt 0 ]]; then echo '本地版卸载不接受删除源码或配置的选项。' >&2; exit 1; fi
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
if [[ -z "$NODE_BIN" && -f "$SOURCE_DIR/.local-install-state.json" ]]; then
  NODE_BIN="$("${CODEX_ZH_PYTHON:-python3}" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("nodeBin",""))' "$SOURCE_DIR/.local-install-state.json")"
fi
if [[ -z "$NODE_BIN" ]]; then echo '请设置 NODE_BIN；未删除任何文件。' >&2; exit 1; fi
"$NODE_BIN" "$SOURCE_DIR/scripts/manage-links.js" remove
echo '卸载完成，源码和设置保留；官方 codex 与 ~/.codex 未被修改。'

