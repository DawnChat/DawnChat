#!/bin/bash

# ============================================================================
# DawnChat Release 构建脚本
#
# 特点:
#   - 仅打包当前平台
#   - Tauri release 模式构建
#   - 启用体积优化
#
# 用法:
#   ./build-release.sh [额外选项]
#
# 示例:
#   ./build-release.sh                  # 默认 release 构建
#   ./build-release.sh --clean          # 清理后构建
#   ./build-release.sh --no-frontend    # 跳过前端构建
#   ./build-release.sh --verbose        # 详细输出
#
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "🚀 DawnChat Release 构建"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 调用主构建脚本，传入 release 模式参数
# --optimize: 优化 Python 包体积
exec "$SCRIPT_DIR/build.sh" --mode release --optimize "$@"


















