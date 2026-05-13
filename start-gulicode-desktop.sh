#!/usr/bin/env bash
# GuLiCode desktop one-click launcher (macOS / Linux)
# 用法: ./start-gulicode-desktop.sh [extra args...]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GULICODE_DIR="$ROOT/GuLiCode"

if [ ! -f "$GULICODE_DIR/package.json" ]; then
    echo "[start-gulicode-desktop] 找不到 GuLiCode 目录: $GULICODE_DIR" >&2
    exit 1
fi

# 1. PATH 上的 bun
BUN="$(command -v bun || true)"

# 2. 常见安装位置
if [ -z "$BUN" ] && [ -x "$HOME/.bun/bin/bun" ]; then
    BUN="$HOME/.bun/bin/bun"
fi

if [ -z "$BUN" ]; then
    cat >&2 <<'EOF'
[start-gulicode-desktop] 未找到 bun，请先安装 Bun:
    curl -fsSL https://bun.com/install | bash
EOF
    exit 1
fi

cd "$GULICODE_DIR"
exec "$BUN" run desktop "$@"
