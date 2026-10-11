#!/usr/bin/env bash
# Install this reviewed local checkout; never download or replace official codex.
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
for arg in "$@"; do
  case "$arg" in
    --no-shadow) : ;;
    --help) echo '安装独立 codex-zh-local 入口；支持 NODE_BIN 和 CODEX_ZH_BIN_DIR。'; exit 0 ;;
    *) echo "未知选项：$arg" >&2; exit 1 ;;
  esac
done
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
if [[ -z "$NODE_BIN" ]]; then echo '未找到 Node.js；请设置 NODE_BIN 指向 Node.js 18+。' >&2; exit 1; fi
"$NODE_BIN" -e 'if(Number(process.versions.node.split(".")[0])<18)process.exit(1)'
"${CODEX_ZH_PYTHON:-python3}" --version
"$NODE_BIN" "$SOURCE_DIR/scripts/validate-data.js"
"$NODE_BIN" "$SOURCE_DIR/scripts/manage-links.js" install "${CODEX_ZH_BIN_DIR:-$HOME/.local/bin}" "$NODE_BIN"
echo '已安装独立 codex-zh-local 入口。官方 codex 和 Codex 配置未被修改。'

