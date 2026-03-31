#!/bin/bash

# ============================================================================
# DawnChat Debug 构建脚本
#
# 特点:
#   - 仅打包当前平台
#   - Tauri debug 模式构建
#   - 不进行 Python 源码加密 (Cython)
#   - 不进行体积优化 (保留完整调试信息)
#   - 自动清理 Cython .so 缓存 (确保使用最新 Python 源码)
#
# 用法:
#   ./build-debug.sh [额外选项]
#
# 示例:
#   ./build-debug.sh                    # 默认 debug 构建
#   ./build-debug.sh --clean            # 清理后构建
#   ./build-debug.sh --no-frontend      # 跳过前端构建
#   ./build-debug.sh --verbose          # 详细输出
#
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TAURI_DIR="$SCRIPT_DIR/apps/desktop/src-tauri"
SIDECAR_DIR="$TAURI_DIR/sidecars/dawnchat-backend"

echo ""
echo "🔧 DawnChat Debug 构建"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# 清理 Cython .so 缓存
# 
# 重要：在 debug 模式下，必须清理 release 模式生成的 .so 文件
# 否则 Python 会优先加载 .so 文件，而不是最新的 .py 源码
# ============================================================================
clean_cython_cache() {
    echo "🧹 清理 Cython .so 缓存..."
    
    if [[ -d "$SIDECAR_DIR/app" ]]; then
        # 查找并删除所有 .so 文件 (Cython 编译产物)
        local so_count=$(find "$SIDECAR_DIR/app" -name "*.so" 2>/dev/null | wc -l | tr -d ' ')
        
        if [[ "$so_count" -gt 0 ]]; then
            find "$SIDECAR_DIR/app" -name "*.so" -delete 2>/dev/null || true
            echo "   ✅ 已删除 $so_count 个 .so 文件"
        fi
        
        # 查找并删除 .c 文件 (Cython 中间产物)
        local c_count=$(find "$SIDECAR_DIR/app" -name "*.c" 2>/dev/null | wc -l | tr -d ' ')
        
        if [[ "$c_count" -gt 0 ]]; then
            find "$SIDECAR_DIR/app" -name "*.c" -delete 2>/dev/null || true
            echo "   ✅ 已删除 $c_count 个 .c 文件"
        fi
        
        if [[ "$so_count" -eq 0 && "$c_count" -eq 0 ]]; then
            echo "   ℹ️  没有发现 Cython 缓存文件"
        fi
    else
        echo "   ℹ️  Sidecar 目录不存在，跳过清理"
    fi
    
    echo ""
}

# 执行清理
clean_cython_cache

# 调用主构建脚本，传入 debug 模式参数
exec "$SCRIPT_DIR/build.sh" --mode debug --cn-mirror "$@"
