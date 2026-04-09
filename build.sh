#!/bin/bash

# ============================================================================
# DawnChat 统一构建脚本 (Python Build Standalone 方案)
#
# 用法:
#   ./build.sh [选项]
#
# 选项:
#   --mode <debug|release>   构建模式 (默认: release)
#   --platform <platform>    目标平台 (默认: 当前平台)
#   --no-frontend           跳过前端构建
#   --no-backend            跳过后端构建
#   --no-tauri              跳过 Tauri 构建
#   --optimize              优化 Python 包体积
#   --clean                 构建前清理
#   --verbose               详细输出
#   --help                  显示帮助信息
#
# 示例:
#   ./build.sh                          # 默认 release 构建
#   ./build.sh --mode debug             # debug 构建
#   ./build.sh --clean --optimize       # 清理后构建并优化
#
# ============================================================================

set -e  # 遇到错误立即退出

# ============ 颜色定义 ============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ============ 日志函数 ============
supports_unicode_output() {
    # Windows CI/终端下优先使用 ASCII，避免 cp1252 等编码导致输出异常
    if [[ "${TARGET_PLATFORM:-}" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        return 1
    fi

    local locale_value="${LC_ALL:-${LC_CTYPE:-${LANG:-}}}"
    locale_value="$(printf '%s' "$locale_value" | tr '[:upper:]' '[:lower:]')"
    if [[ "$locale_value" == *"utf-8"* || "$locale_value" == *"utf8"* ]]; then
        return 0
    fi
    return 1
}

print_info() {
    if supports_unicode_output; then
        echo -e "${BLUE}ℹ️  $1${NC}"
    else
        echo -e "${BLUE}[INFO] $1${NC}"
    fi
}

print_success() {
    if supports_unicode_output; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${GREEN}[OK] $1${NC}"
    fi
}

print_warning() {
    if supports_unicode_output; then
        echo -e "${YELLOW}⚠️  $1${NC}"
    else
        echo -e "${YELLOW}[WARN] $1${NC}"
    fi
}

print_error() {
    if supports_unicode_output; then
        echo -e "${RED}❌ $1${NC}"
    else
        echo -e "${RED}[ERROR] $1${NC}"
    fi
}

print_step() {
    if supports_unicode_output; then
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}📦 $1${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    else
        echo -e "${CYAN}--------------------------------------------------${NC}"
        echo -e "${CYAN}[STEP] $1${NC}"
        echo -e "${CYAN}--------------------------------------------------${NC}"
    fi
}

resolve_runtime_asset_dir() {
    local preferred="$1"
    shift || true
    if [[ -e "$preferred" ]]; then
        echo "$preferred"
        return 0
    fi
    local fallback=""
    for fallback in "$@"; do
        if [[ -n "$fallback" && -e "$fallback" ]]; then
            echo "$fallback"
            return 0
        fi
    done
    echo "$preferred"
    return 1
}

calc_sha256() {
    local file_path="$1"
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$file_path" | awk '{print $1}'
        return 0
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$file_path" | awk '{print $1}'
        return 0
    fi
    print_error "未找到 sha256 计算工具（shasum/sha256sum）"
    return 1
}

load_manifest_asset() {
    local asset="$1"
    local platform="$2"
    eval "$(
        python3 "$PROJECT_ROOT/scripts/runtime_asset_manifest.py" get \
            --manifest "$RUNTIME_ASSETS_MANIFEST_PATH" \
            --asset "$asset" \
            --platform "$platform" \
            --format shell
    )"
    if [[ -z "${ASSET_URL:-}" || -z "${ASSET_FILENAME:-}" || -z "${ASSET_SHA256:-}" ]]; then
        print_error "Manifest 资产字段不完整: asset=$asset platform=$platform"
        exit 1
    fi
}

verify_checksum() {
    local file_path="$1"
    local expected_sha="$2"
    local actual_sha
    actual_sha="$(calc_sha256 "$file_path")"
    if [[ "$actual_sha" != "$expected_sha" ]]; then
        print_error "SHA256 校验失败: $file_path"
        print_error "expected=$expected_sha"
        print_error "actual=$actual_sha"
        return 1
    fi
}

# ============ 默认配置 ============
BUILD_MODE="release"
TARGET_PLATFORM=""
BUILD_FRONTEND=true
BUILD_BACKEND=true
BUILD_TAURI=true
ENABLE_OPTIMIZE=false
EMBED_CHROMIUM=false
ENABLE_VERBOSE_IMPORT=false
CLEAN_BEFORE_BUILD=false
VERBOSE=false
ENABLE_MLX=false
ENABLE_LLAMACPP=false
USER_SET_OPTIMIZE=false
SIGN_MACOS=false
NOTARIZE_MACOS=false
DMG_ONLY=false
FORCE_ARM64=false
ENABLE_KOKORO_MODEL=false
NOTARY_POLL_SECONDS=30
NOTARY_TIMEOUT_MINUTES=240
NOTARY_PROFILE="${NOTARY_PROFILE:-dawnchat-notary}"
MACOS_SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:-}"

# PBS 版本与下载 URL 统一由 runtime manifest 提供

# MLX 依赖版本（可通过环境变量覆盖）
MLX_VERSION="${MLX_VERSION:-0.30.4}"
MLX_LM_VERSION="${MLX_LM_VERSION:-0.30.4}"
MLX_VLM_VERSION="${MLX_VLM_VERSION:-0.3.9}"
MLX_WITH_VLM="${MLX_WITH_VLM:-true}"

# 目录配置
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/packages/backend-kernel"
SDK_DIR="$PROJECT_ROOT/dawnchat-plugins/sdk"
ASSISTANT_SDK_DIR="$PROJECT_ROOT/dawnchat-plugins/assistant-sdk"
ASSISTANT_WORKSPACE_DIR="$PROJECT_ROOT/dawnchat-plugins/assistant-workspace"
FRONTEND_DIR="$PROJECT_ROOT/apps/frontend"
TAURI_DIR="$PROJECT_ROOT/apps/desktop/src-tauri"
SIDECAR_DIR="$TAURI_DIR/sidecars/dawnchat-backend"
MACOS_ENTITLEMENTS_FILE="${MACOS_ENTITLEMENTS_FILE:-$TAURI_DIR/Entitlements.plist}"
CACHE_DIR="$PROJECT_ROOT/.cache/pbs"
OFFICIAL_PLUGINS_DIR="$PROJECT_ROOT/dawnchat-plugins/official-plugins"
RUNTIME_ASSETS_DIR="${DAWNCHAT_RUNTIME_ASSETS_DIR:-$PROJECT_ROOT/runtime-assets}"
LLAMACPP_ASSETS_DIR="$RUNTIME_ASSETS_DIR/llamacpp"
TTS_MODELS_ASSETS_DIR="$RUNTIME_ASSETS_DIR/tts-models"
UV_BINARY_ASSETS_DIR="$RUNTIME_ASSETS_DIR/uv-binary"
BUN_BINARY_ASSETS_DIR="$RUNTIME_ASSETS_DIR/bun-bin"
OPENCODE_BINARY_ASSETS_DIR="$RUNTIME_ASSETS_DIR/opencode-bin"
RUNTIME_ASSETS_MANIFEST_PATH="${DAWNCHAT_RUNTIME_ASSETS_MANIFEST_PATH:-$PROJECT_ROOT/scripts/runtime-assets-manifest.json}"

ASSISTANT_WORKSPACE_READY=false
ASSISTANT_TEMPLATE_DIST_READY=false

# Llama.cpp 版本
LLAMA_VERSION="b7204"
KOKORO_MODEL_DIR_NAME="${KOKORO_MODEL_DIR_NAME:-kokoro-multi-lang-v1_1}"

# ============ 帮助信息 ============
show_help() {
    cat << EOF
DawnChat 统一构建脚本 (Python Build Standalone 方案)

用法:
    $0 [选项]

选项:
    --mode <debug|release>   构建模式 (默认: release)
    --platform <platform>    目标平台:
                               aarch64-apple-darwin    (macOS ARM64)
                               x86_64-apple-darwin     (macOS Intel)
                               x86_64-unknown-linux-gnu (Linux x64)
                               x86_64-pc-windows-msvc   (Windows x64)
    --no-frontend           跳过前端构建
    --no-backend            跳过后端构建
    --no-tauri              跳过 Tauri 构建
    --optimize              优化 Python 包体积
    --embed-chromium        嵌入 Chromium 浏览器 (用于爬虫功能)
    --enable-verbose-import 开启详细的 Python 导入日志 (PYTHONVERBOSE)
    --with-mlx              安装 MLX 运行时依赖
    --with-llamacpp         内置 llama.cpp 二进制（默认关闭）
    --mirror <url>          指定 PyPI 镜像地址
    --cn-mirror             使用国内镜像 (清华源) 加速下载
    --clean                 构建前清理所有产物
    --sign-macos            启用 macOS Developer ID 签名
    --notarize-macos        启用 macOS 公证（隐含签名）
    --notary-profile <name> 指定 notarytool keychain profile
    --signing-identity <id> 指定 macOS 签名证书名称
    --dmg-only              仅构建 dmg 产物
    --arm64                 强制以 macOS ARM64 目标构建
    --with-kokoro-model     内置 Kokoro TTS 模型（默认关闭）
    --notary-poll-seconds <n>      公证状态轮询间隔秒数 (默认: 30)
    --notary-timeout-minutes <n>   公证轮询超时分钟数 (默认: 240)
    --verbose               详细输出
    --help                  显示此帮助信息

示例:
    $0                              # 默认 release 构建
    $0 --cn-mirror                  # 使用国内镜像加速
    $0 --mode debug                 # debug 构建
    $0 --clean --optimize           # 清理后构建并优化

环境变量:
    PYPI_MIRROR     PyPI 镜像地址 (例: https://pypi.tuna.tsinghua.edu.cn/simple)

EOF
}

# ============ 参数解析 ============
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --mode)
                BUILD_MODE="$2"
                shift 2
                ;;
            --platform)
                TARGET_PLATFORM="$2"
                shift 2
                ;;
            --no-frontend)
                BUILD_FRONTEND=false
                shift
                ;;
            --no-backend)
                BUILD_BACKEND=false
                shift
                ;;
            --no-tauri)
                BUILD_TAURI=false
                shift
                ;;
            --optimize)
                ENABLE_OPTIMIZE=true
                USER_SET_OPTIMIZE=true
                shift
                ;;
            --embed-chromium)
                EMBED_CHROMIUM=true
                shift
                ;;
            --enable-verbose-import)
                ENABLE_VERBOSE_IMPORT=true
                shift
                ;;
            --with-mlx)
                ENABLE_MLX=true
                shift
                ;;
            --with-llamacpp)
                ENABLE_LLAMACPP=true
                shift
                ;;
            --mirror)
                PYPI_MIRROR="$2"
                shift 2
                ;;
            --cn-mirror)
                PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
                shift
                ;;
            --clean)
                CLEAN_BEFORE_BUILD=true
                shift
                ;;
            --sign-macos)
                SIGN_MACOS=true
                shift
                ;;
            --notarize-macos)
                SIGN_MACOS=true
                NOTARIZE_MACOS=true
                shift
                ;;
            --notary-profile)
                NOTARY_PROFILE="$2"
                shift 2
                ;;
            --signing-identity)
                MACOS_SIGNING_IDENTITY="$2"
                shift 2
                ;;
            --dmg-only)
                DMG_ONLY=true
                shift
                ;;
            --arm64)
                FORCE_ARM64=true
                shift
                ;;
            --with-kokoro-model)
                ENABLE_KOKORO_MODEL=true
                shift
                ;;
            --notary-poll-seconds)
                NOTARY_POLL_SECONDS="$2"
                shift 2
                ;;
            --notary-timeout-minutes)
                NOTARY_TIMEOUT_MINUTES="$2"
                shift 2
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                print_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 验证构建模式
    if [[ "$BUILD_MODE" != "debug" && "$BUILD_MODE" != "release" ]]; then
        print_error "无效的构建模式: $BUILD_MODE (必须是 debug 或 release)"
        exit 1
    fi
    if ! [[ "$NOTARY_POLL_SECONDS" =~ ^[0-9]+$ ]] || [[ "$NOTARY_POLL_SECONDS" -lt 5 ]]; then
        print_error "--notary-poll-seconds 必须是大于等于 5 的整数"
        exit 1
    fi
    if ! [[ "$NOTARY_TIMEOUT_MINUTES" =~ ^[0-9]+$ ]] || [[ "$NOTARY_TIMEOUT_MINUTES" -lt 10 ]]; then
        print_error "--notary-timeout-minutes 必须是大于等于 10 的整数"
        exit 1
    fi
}

# ============ 平台检测 ============
detect_platform() {
    if [[ "$FORCE_ARM64" == true ]]; then
        echo "aarch64-apple-darwin"
        return
    fi

    if [[ -n "$TARGET_PLATFORM" ]]; then
        echo "$TARGET_PLATFORM"
        return
    fi
    
    local os=$(uname -s)
    local arch=$(uname -m)
    
    case "$os" in
        Darwin)
            if [[ "$arch" == "arm64" ]]; then
                echo "aarch64-apple-darwin"
            else
                echo "x86_64-apple-darwin"
            fi
            ;;
        Linux)
            if [[ "$arch" == "aarch64" ]]; then
                echo "aarch64-unknown-linux-gnu"
            else
                echo "x86_64-unknown-linux-gnu"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            if [[ "$arch" == "ARM64" ]]; then
                echo "aarch64-pc-windows-msvc"
            else
                echo "x86_64-pc-windows-msvc"
            fi
            ;;
        *)
            print_error "不支持的操作系统: $os"
            exit 1
            ;;
    esac
}

# ============ 获取 Llama.cpp 目录名 ============
get_llamacpp_dir() {
    local platform="$1"
    
    case "$platform" in
        aarch64-apple-darwin)
            echo "llama-${LLAMA_VERSION}-bin-macos-arm64"
            ;;
        x86_64-apple-darwin)
            echo "llama-${LLAMA_VERSION}-bin-macos-x64"
            ;;
        x86_64-unknown-linux-gnu|aarch64-unknown-linux-gnu)
            echo "llama-${LLAMA_VERSION}-bin-ubuntu-x64"
            ;;
        x86_64-pc-windows-msvc)
            echo "llama-${LLAMA_VERSION}-bin-win-cpu-x64"
            ;;
        aarch64-pc-windows-msvc)
            echo "llama-${LLAMA_VERSION}-bin-win-cpu-arm64"
            ;;
        *)
            echo ""
            ;;
    esac
}

# ============ 检查依赖 ============
check_prerequisites() {
    print_step "检查构建依赖"
    
    local missing=()
    
    # 检查 pnpm
    if ! command -v pnpm &> /dev/null; then
        missing+=("pnpm")
    fi
    
    # 检查 poetry
    if ! command -v poetry &> /dev/null; then
        # 尝试常见路径
        if [[ -f "$HOME/Library/Python/3.10/bin/poetry" ]]; then
            export PATH="$HOME/Library/Python/3.10/bin:$PATH"
        elif [[ -f "$HOME/.local/bin/poetry" ]]; then
            export PATH="$HOME/.local/bin:$PATH"
        else
            missing+=("poetry")
        fi
    fi
    
    # 检查 Rust (Tauri 需要)
    if [[ "$BUILD_TAURI" == true ]]; then
        if ! command -v rustc &> /dev/null; then
            missing+=("rustc (Rust)")
        fi
    fi
    
    # 检查 curl (下载 PBS)
    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi
    
    if [[ ${#missing[@]} -ne 0 ]]; then
        print_error "缺少必要依赖: ${missing[*]}"
        echo ""
        echo "安装方法:"
        echo "  pnpm:   npm install -g pnpm"
        echo "  poetry: curl -sSL https://install.python-poetry.org | python3 -"
        echo "  rust:   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        exit 1
    fi

    if [[ "$SIGN_MACOS" == true || "$NOTARIZE_MACOS" == true ]]; then
        if [[ "$(uname -s)" != "Darwin" ]]; then
            print_error "macOS 签名与公证仅支持在 macOS 环境执行"
            exit 1
        fi
        local apple_tools=("security" "codesign" "spctl" "xcrun")
        for tool in "${apple_tools[@]}"; do
            if ! command -v "$tool" &> /dev/null; then
                print_error "缺少 Apple 工具: $tool"
                exit 1
            fi
        done
    fi
    
    print_success "所有依赖已满足"
}

# ============ 清理构建产物 ============
clean_build() {
    print_step "清理构建产物"
    
    # 清理 sidecar 目录
    if [[ -d "$SIDECAR_DIR" ]]; then
        rm -rf "$SIDECAR_DIR"
        print_info "已删除: $SIDECAR_DIR"
    fi
    
    # 清理前端构建产物
    if [[ -d "$FRONTEND_DIR/dist" ]]; then
        rm -rf "$FRONTEND_DIR/dist"
        print_info "已删除: $FRONTEND_DIR/dist"
    fi
    
    # 清理 Tauri 构建产物
    if [[ -d "$TAURI_DIR/target/release/bundle" ]]; then
        rm -rf "$TAURI_DIR/target/release/bundle"
        print_info "已删除: $TAURI_DIR/target/release/bundle"
    fi
    if [[ -d "$TAURI_DIR/target/debug/bundle" ]]; then
        rm -rf "$TAURI_DIR/target/debug/bundle"
        print_info "已删除: $TAURI_DIR/target/debug/bundle"
    fi
    
    print_success "清理完成"
}

# ============ 下载 PBS Python ============
download_pbs_python() {
    local platform="$1"
    
    print_step "下载 Python Build Standalone ($platform)"

    load_manifest_asset "pbs-python" "$platform"
    local filename="$ASSET_FILENAME"
    local url="$ASSET_URL"
    local checksum="$ASSET_SHA256"
    local cache_file="$CACHE_DIR/$filename"
    
    # 创建缓存目录
    mkdir -p "$CACHE_DIR"
    
    # 检查缓存
    if [[ -f "$cache_file" ]]; then
        if ! verify_checksum "$cache_file" "$checksum"; then
            print_warning "缓存文件 SHA256 校验失败，重新下载..."
            rm -f "$cache_file"
        else
            local file_size=$(stat -f%z "$cache_file" 2>/dev/null || stat -c%s "$cache_file" 2>/dev/null || echo "0")
            print_info "使用缓存: $cache_file (大小: $(($file_size / 1024 / 1024))MB)"
        fi
    fi
    
    if [[ ! -f "$cache_file" ]]; then
        print_info "下载: $url"
        curl -L --progress-bar --fail "$url" -o "$cache_file"
        
        # 验证下载成功
        if [[ ! -f "$cache_file" ]]; then
            print_error "下载失败: 文件不存在"
            exit 1
        fi
        
        local file_size=$(stat -f%z "$cache_file" 2>/dev/null || stat -c%s "$cache_file" 2>/dev/null || echo "0")
        if [[ "$file_size" -lt 1000000 ]]; then
            print_error "下载失败: 文件大小异常 (${file_size} bytes)"
            rm -f "$cache_file"
            exit 1
        fi
        if ! verify_checksum "$cache_file" "$checksum"; then
            rm -f "$cache_file"
            exit 1
        fi
    fi
    
    # 创建 sidecar 目录
    mkdir -p "$SIDECAR_DIR"
    
    # 解压
    print_info "解压到: $SIDECAR_DIR"
    if ! tar -xzf "$cache_file" -C "$SIDECAR_DIR"; then
        print_error "解压失败: 文件可能已损坏"
        rm -f "$cache_file"
        exit 1
    fi
    
    # 设置执行权限
    if [[ -f "$SIDECAR_DIR/python/bin/python3.11" ]]; then
        chmod +x "$SIDECAR_DIR/python/bin/python3.11"
        chmod +x "$SIDECAR_DIR/python/bin/pip3.11" 2>/dev/null || true
    fi
    
    print_success "PBS Python 已安装"
}

poetry_supports_lock_check() {
    local help_text
    help_text="$(poetry check --help 2>/dev/null || true)"
    [[ "$help_text" == *"--lock"* ]]
}

poetry_supports_lock_subcommand_check() {
    local help_text
    help_text="$(poetry lock --help 2>/dev/null || true)"
    [[ "$help_text" == *"--check"* ]]
}

ensure_poetry_lock_consistent_or_exit() {
    local project_dir="$1"
    local hint_cmd="cd $project_dir && poetry lock"
    cd "$project_dir"
    if poetry_supports_lock_check; then
        if poetry check --lock >/dev/null 2>&1; then
            return 0
        fi
        print_error "检测到 pyproject.toml 与 poetry.lock 不一致"
        print_error "请先运行: $hint_cmd"
        exit 1
    fi
    if poetry_supports_lock_subcommand_check; then
        if poetry lock --check >/dev/null 2>&1; then
            return 0
        fi
        print_error "检测到 pyproject.toml 与 poetry.lock 不一致"
        print_error "请先运行: $hint_cmd"
        exit 1
    fi
    print_warning "当前 Poetry 不支持 lock 一致性子命令，跳过一致性命令校验"
}

# ============ 安装 Python 依赖 ============
install_python_deps() {
    print_step "安装 Python 依赖"
    
    local python_path="$SIDECAR_DIR/python/bin/python3.11"
    local pip_cmd=()
    
    # Windows 路径
    if [[ "$TARGET_PLATFORM" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        python_path="$SIDECAR_DIR/python/python.exe"
    fi

    if [[ ! -f "$python_path" ]]; then
        print_error "未找到 Python 可执行文件: $python_path"
        exit 1
    fi

    # 使用 python -m pip，避免依赖平台特定的 pip 可执行文件路径
    pip_cmd=("$python_path" -m pip)
    
    cd "$BACKEND_DIR"
    
    local release_requirements_path="$BACKEND_DIR/requirements-release.txt"
    local install_requirements_path="requirements.txt"

    # 检查 lock 文件是否存在（不使用 mtime，避免 CI checkout 时间戳误报）
    local pyproject_path="$BACKEND_DIR/pyproject.toml"
    local lock_path="$BACKEND_DIR/poetry.lock"

    if [[ ! -f "$pyproject_path" || ! -f "$lock_path" ]]; then
        print_error "缺少 pyproject.toml 或 poetry.lock，无法执行可复现依赖安装"
        exit 1
    fi

    ensure_poetry_lock_consistent_or_exit "$BACKEND_DIR"
    cd "$BACKEND_DIR"

    # 检查 poetry export 是否可用
    if ! poetry export --help &> /dev/null; then
        print_warning "poetry export 命令不可用，尝试安装 poetry-plugin-export..."
        if poetry self add poetry-plugin-export; then
             print_success "插件安装成功"
        else
             print_error "插件安装失败，请手动运行: poetry self add poetry-plugin-export"
             exit 1
        fi
    fi

    if [[ "$BUILD_MODE" == "release" ]]; then
        if [[ ! -f "$release_requirements_path" ]]; then
            print_error "缺少 release 依赖锁定文件: $release_requirements_path"
            print_error "请执行: cd $BACKEND_DIR && poetry export -f requirements.txt -o requirements-release.txt"
            exit 1
        fi

        local temp_export
        temp_export="$(mktemp)"
        poetry export -f requirements.txt -o "$temp_export"
        if ! cmp -s "$temp_export" "$release_requirements_path"; then
            rm -f "$temp_export"
            print_error "requirements-release.txt 与 poetry.lock 不一致"
            print_error "请执行: cd $BACKEND_DIR && poetry export -f requirements.txt -o requirements-release.txt"
            exit 1
        fi
        rm -f "$temp_export"
        install_requirements_path="$release_requirements_path"
        print_info "release 模式使用锁定依赖: $install_requirements_path"
    else
        print_info "导出开发依赖列表..."
        poetry export -f requirements.txt --without-hashes -o requirements.txt

        # 确保 gradio/nicegui 版本与 lock 文件一致
        print_info "同步 PBS 依赖版本..."
        python3 "$PROJECT_ROOT/scripts/ensure_pbs_deps.py" "$BACKEND_DIR/poetry.lock" "requirements.txt"
        install_requirements_path="requirements.txt"
    fi

    local mlx_specs=()
    if [[ "$ENABLE_MLX" == true ]]; then
        if [[ "$TARGET_PLATFORM" == *"apple-darwin"* || "$(uname -s)" == "Darwin" ]]; then
            mlx_specs+=("mlx>=${MLX_VERSION}" "mlx-lm>=${MLX_LM_VERSION}")
            if [[ "$(echo "$MLX_WITH_VLM" | tr '[:upper:]' '[:lower:]')" == "true" ]]; then
                mlx_specs+=("mlx-vlm>=${MLX_VLM_VERSION}")
            fi
        else
            print_warning "当前平台非 macOS，跳过 MLX 依赖安装"
        fi
    fi
    
    # 准备镜像参数
    local mirror_args=()
    if [[ -n "$PYPI_MIRROR" ]]; then
        mirror_args+=("--index-url" "$PYPI_MIRROR")
    fi

    # 升级 pip（release 构建保持最小变动，避免引入额外漂移）
    if [[ "$BUILD_MODE" != "release" ]]; then
        print_info "升级 pip..."
        "${pip_cmd[@]}" install --upgrade pip --quiet "${mirror_args[@]}"
    fi
    
    # 安装依赖
    print_info "安装依赖 (这可能需要几分钟)..."
    local pip_args=("-r" "$install_requirements_path" "--no-cache-dir")
    if [[ "$BUILD_MODE" == "release" ]]; then
        pip_args+=("--require-hashes")
    fi
    pip_args+=("${mirror_args[@]}")
    
    if [[ "$VERBOSE" == true ]]; then
        "${pip_cmd[@]}" install "${pip_args[@]}"
    else
        "${pip_cmd[@]}" install "${pip_args[@]}" --quiet
    fi

    if [[ "${#mlx_specs[@]}" -gt 0 ]]; then
        print_info "安装 MLX 依赖..."
        "${pip_cmd[@]}" install --upgrade --no-deps --no-cache-dir --quiet "${mlx_specs[@]}" "${mirror_args[@]}"
    fi

    # 安装 DawnChat SDK (用于 Plugin)
    print_info "安装 DawnChat SDK..."
    if [[ -d "$SDK_DIR" ]]; then
        local sdk_args=("$SDK_DIR" "--no-cache-dir" "--quiet")
        if [[ "$BUILD_MODE" == "release" ]]; then
            sdk_args+=("--no-deps")
        fi
        "${pip_cmd[@]}" install "${sdk_args[@]}" "${mirror_args[@]}"
        print_info "DawnChat SDK 安装成功"
    else
        print_warning "未找到 SDK 目录: $SDK_DIR，跳过安装"
    fi

    # 基础依赖导入验证（宿主最小依赖）
    print_info "验证基础依赖..."
    if ! "$python_path" -c "
import sys
try:
    import fastapi
    import uvicorn
    import pydantic
    print('OK: base dependencies validation passed')
except Exception as e:
    print(f'ERROR: validation failed: {e}')
    sys.exit(1)
"; then
        print_error "基础依赖验证失败，请检查上方报错信息"
        exit 1
    fi
    
    cd "$PROJECT_ROOT"
    
    print_success "Python 依赖安装完成"
}

# ============ 复制源代码 ============
copy_source_code() {
    print_step "复制 Python 源代码"
    
    local src_dir="$BACKEND_DIR/app"
    local dest_dir="$SIDECAR_DIR/app"
    
    # 复制源代码
    mkdir -p "$dest_dir"
    cp -r "$src_dir"/* "$dest_dir/"

    # 清理运行时无关缓存文件，减少 sidecar 体积
    find "$dest_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$dest_dir" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
    
    # 复制配置文件
    if [[ -d "$BACKEND_DIR/data" ]]; then
        cp -r "$BACKEND_DIR/data" "$SIDECAR_DIR/"
    fi
    
    print_success "源代码复制完成"
}

# ============ 优化 Python 包体积 ============
optimize_python() {
    if [[ "$ENABLE_OPTIMIZE" != true ]]; then
        return 0
    fi
    
    print_step "优化 Python 包体积"
    
    local python_dir="$SIDECAR_DIR/python"
    local python_path="$python_dir/bin/python3.11"
    local is_windows_target=false
    if [[ "$TARGET_PLATFORM" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        python_path="$python_dir/python.exe"
        is_windows_target=true
    fi
    
    # 使用 optimize_python.py 脚本
    if [[ -f "$BACKEND_DIR/scripts/optimize_python.py" ]]; then
        "$python_path" "$BACKEND_DIR/scripts/optimize_python.py" "$python_dir"
    else
        # 内联优化
        print_info "删除测试文件..."
        find "$python_dir" -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
        find "$python_dir" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
        
        print_info "删除 __pycache__..."
        find "$python_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        
        print_info "删除不需要的模块..."
        if [[ "$is_windows_target" == true ]]; then
            rm -rf "$python_dir/Lib/tkinter" 2>/dev/null || true
            rm -rf "$python_dir/Lib/idlelib" 2>/dev/null || true
            rm -rf "$python_dir/Lib/turtledemo" 2>/dev/null || true
        else
            rm -rf "$python_dir/lib/python3.11/tkinter" 2>/dev/null || true
            rm -rf "$python_dir/lib/python3.11/idlelib" 2>/dev/null || true
            rm -rf "$python_dir/lib/python3.11/turtledemo" 2>/dev/null || true
        fi
    fi
    
    # 计算优化后大小
    local size=$(du -sh "$SIDECAR_DIR" | cut -f1)
    print_success "优化完成，当前大小: $size"
}

# ============ 复制 Llama.cpp 二进制 ============
copy_llamacpp_binary() {
    local platform="$1"
    
    print_step "复制 Llama.cpp 二进制"
    
    local llamacpp_dir_name=$(get_llamacpp_dir "$platform")
    
    if [[ -z "$llamacpp_dir_name" ]]; then
        print_warning "未找到当前平台的 Llama.cpp 二进制，跳过"
        return 0
    fi
    
    local assets_dir
    assets_dir="$(resolve_runtime_asset_dir "$LLAMACPP_ASSETS_DIR" "$BACKEND_DIR/llamacpp")"
    local src_path="$assets_dir/$llamacpp_dir_name"
    local dest_path="$SIDECAR_DIR/llamacpp"
    
    if [[ ! -d "$src_path" ]]; then
        print_warning "Llama.cpp 源目录不存在: $src_path"
        return 0
    fi
    
    mkdir -p "$dest_path"
    cp -r "$src_path" "$dest_path/"
    
    # 设置执行权限
    if [[ -f "$dest_path/$llamacpp_dir_name/bin/llama-server" ]]; then
        chmod +x "$dest_path/$llamacpp_dir_name/bin/llama-server"
    fi
    
    print_success "Llama.cpp 二进制复制完成"
}

copy_tts_kokoro_model() {
    if [[ "$ENABLE_KOKORO_MODEL" != true ]]; then
        print_info "跳过 Kokoro TTS 模型内置"
        return 0
    fi

    print_step "复制 Kokoro TTS 模型"

    local source_dir=""
    local candidate_dirs=(
        "$TTS_MODELS_ASSETS_DIR/$KOKORO_MODEL_DIR_NAME"
        "$BACKEND_DIR/assets/tts/$KOKORO_MODEL_DIR_NAME"
        "$PROJECT_ROOT/download/$KOKORO_MODEL_DIR_NAME"
    )
    local candidate=""
    for candidate in "${candidate_dirs[@]}"; do
        if [[ -f "$candidate/model.onnx" ]]; then
            source_dir="$candidate"
            break
        fi
    done
    if [[ -z "$source_dir" ]]; then
        print_error "未找到 Kokoro 模型目录，无法内置 TTS"
        return 1
    fi

    local target_dir="$SIDECAR_DIR/tts-models/$KOKORO_MODEL_DIR_NAME"
    rm -rf "$target_dir"
    mkdir -p "$target_dir"

    if [[ -f "$source_dir/model.onnx" ]]; then
        cp "$source_dir/model.onnx" "$target_dir/model.onnx"
    else
        print_error "Kokoro 模型缺少 onnx 文件，无法内置: $source_dir"
        return 1
    fi

    local required_files=(
        "voices.bin"
        "tokens.txt"
        "lexicon-us-en.txt"
        "lexicon-gb-en.txt"
        "lexicon-zh.txt"
        "number-zh.fst"
        "date-zh.fst"
        "phone-zh.fst"
    )
    local file_name=""
    for file_name in "${required_files[@]}"; do
        if [[ -f "$source_dir/$file_name" ]]; then
            cp "$source_dir/$file_name" "$target_dir/$file_name"
        fi
    done

    if [[ -d "$source_dir/espeak-ng-data" ]]; then
        cp -R "$source_dir/espeak-ng-data" "$target_dir/espeak-ng-data"
    fi
    if [[ -d "$source_dir/dict" ]]; then
        cp -R "$source_dir/dict" "$target_dir/dict"
    fi

    local model_size
    model_size=$(du -sh "$target_dir" | cut -f1)
    print_success "Kokoro TTS 模型复制完成 -> $target_dir ($model_size)"
}

# ============ 嵌入 Chromium ============
embed_chromium() {
    if [[ "$EMBED_CHROMIUM" != true ]]; then
        return 0
    fi
    
    print_step "嵌入 Chromium 浏览器"
    
    local python_path="$SIDECAR_DIR/python/bin/python3.11"
    # Windows adapt
    if [[ "$TARGET_PLATFORM" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        python_path="$SIDECAR_DIR/python/python.exe"
    fi
    
    # 临时目录用于下载浏览器
    local temp_browsers_dir="$CACHE_DIR/browsers"
    mkdir -p "$temp_browsers_dir"
    
    print_info "正在下载 Chromium (Playwright)..."
    
    # 设置 PLAYWRIGHT_BROWSERS_PATH 环境变量
    export PLAYWRIGHT_BROWSERS_PATH="$temp_browsers_dir"
    
    if ! "$python_path" -m playwright install chromium; then
        print_error "Chromium 下载失败"
        return 1
    fi
    
    # 查找下载的 chromium 目录
    local chromium_dir=$(find "$temp_browsers_dir" -maxdepth 1 -type d -name "chromium-*" | head -n 1)
    
    if [[ -z "$chromium_dir" ]]; then
        print_error "未找到下载的 Chromium 目录"
        return 1
    fi
    
    local dir_name=$(basename "$chromium_dir")
    print_info "找到浏览器: $dir_name"
    
    # 目标目录
    local dest_parent="$SIDECAR_DIR/playwright/driver/package/.local-browsers"
    mkdir -p "$dest_parent"
    
    local dest_path="$dest_parent/$dir_name"
    
    if [[ -d "$dest_path" ]]; then
        print_info "目标已存在，覆盖..."
        rm -rf "$dest_path"
    fi
    
    print_info "复制到 Sidecar: $dest_path"
    cp -r "$chromium_dir" "$dest_path"
    
    # 恢复环境变量
    unset PLAYWRIGHT_BROWSERS_PATH
    
    print_success "Chromium 嵌入完成"
}

# ============ 复制 uv 二进制 ============
copy_uv_binary() {
    local platform="$1"
    
    print_step "复制 uv 二进制 (Plugin 依赖管理)"
    
    local uv_dir=""
    case "$platform" in
        aarch64-apple-darwin)
            uv_dir="uv-aarch64-apple-darwin"
            ;;
        x86_64-apple-darwin)
            uv_dir="uv-x86_64-apple-darwin"
            ;;
        x86_64-unknown-linux-gnu)
            uv_dir="uv-x86_64-unknown-linux-gnu"
            ;;
        aarch64-unknown-linux-gnu)
            uv_dir="uv-aarch64-unknown-linux-gnu"
            ;;
        x86_64-pc-windows-msvc)
            uv_dir="uv-x86_64-pc-windows-msvc"
            ;;
        aarch64-pc-windows-msvc)
            uv_dir="uv-aarch64-pc-windows-msvc"
            ;;
        *)
            print_warning "未识别的平台，跳过 uv 复制: $platform"
            return 0
            ;;
    esac
    
    local assets_dir
    assets_dir="$(resolve_runtime_asset_dir "$UV_BINARY_ASSETS_DIR" "$BACKEND_DIR/uv-binary")"
    local src_path="$assets_dir/$uv_dir"
    local dest_path="$SIDECAR_DIR/uv-binary"
    
    if [[ ! -d "$src_path" ]]; then
        print_warning "uv 源目录不存在: $src_path"
        return 0
    fi
    
    mkdir -p "$dest_path"
    cp -r "$src_path"/* "$dest_path/"
    
    # 设置执行权限
    chmod +x "$dest_path/uv" 2>/dev/null || true
    chmod +x "$dest_path/uvx" 2>/dev/null || true
    
    print_success "uv 二进制复制完成 -> $dest_path"
}

# ============ 复制 bun 二进制 ============
copy_bun_binary() {
    local platform="$1"

    print_step "复制 bun 二进制 (Plugin Preview 热重载)"

    local bun_dir=""
    local bun_name="bun"
    case "$platform" in
        aarch64-apple-darwin)
            bun_dir="bun-darwin-aarch64"
            ;;
        x86_64-apple-darwin)
            bun_dir="bun-darwin-x64"
            ;;
        x86_64-unknown-linux-gnu)
            bun_dir="bun-linux-x64"
            ;;
        aarch64-unknown-linux-gnu)
            bun_dir="bun-linux-aarch64"
            ;;
        x86_64-pc-windows-msvc)
            bun_dir="bun-windows-x64"
            bun_name="bun.exe"
            ;;
        *)
            print_warning "未识别的平台，跳过 bun 复制: $platform"
            return 0
            ;;
    esac

    local assets_dir
    assets_dir="$(resolve_runtime_asset_dir "$BUN_BINARY_ASSETS_DIR" "$PROJECT_ROOT/binary/bun-bin")"
    local src_path="$assets_dir/$bun_dir/$bun_name"
    local dest_dir="$SIDECAR_DIR/bun-bin"
    local dest_path="$dest_dir/$bun_name"

    if [[ ! -f "$src_path" ]]; then
        print_warning "bun 源文件不存在: $src_path"
        return 0
    fi

    mkdir -p "$dest_dir"
    cp "$src_path" "$dest_path"
    chmod +x "$dest_path" 2>/dev/null || true

    print_success "bun 二进制复制完成 -> $dest_path"
}

template_uses_assistant_sdk() {
    local package_json_path="$1"
    if [[ ! -f "$package_json_path" ]]; then
        return 1
    fi
    python3 - "$package_json_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

for section in ("dependencies", "devDependencies"):
    deps = payload.get(section)
    if not isinstance(deps, dict):
        continue
    for package_name in ("@dawnchat/assistant-core", "@dawnchat/host-orchestration-sdk"):
        if str(deps.get(package_name) or "").strip() == "workspace:*":
            raise SystemExit(0)
raise SystemExit(1)
PY
}

ensure_assistant_workspace_deps() {
    local bun_bin="$1"
    if [[ "$ASSISTANT_WORKSPACE_READY" == true ]]; then
        return 0
    fi
    if [[ ! -x "$bun_bin" ]]; then
        print_error "缺少 bun 二进制，无法初始化 assistant workspace: $bun_bin"
        exit 1
    fi
    if [[ ! -f "$ASSISTANT_WORKSPACE_DIR/package.json" ]]; then
        print_error "缺少 assistant workspace 配置: $ASSISTANT_WORKSPACE_DIR/package.json"
        exit 1
    fi
    print_info "安装 assistant workspace 依赖..."
    (cd "$ASSISTANT_WORKSPACE_DIR" && "$bun_bin" install --frozen-lockfile)
    ASSISTANT_WORKSPACE_READY=true
}

run_assistant_workspace_script() {
    local bun_bin="$1"
    local script_name="$2"
    ensure_assistant_workspace_deps "$bun_bin"
    print_info "执行 assistant workspace 脚本: $script_name"
    (cd "$ASSISTANT_WORKSPACE_DIR" && "$bun_bin" run "$script_name")
}

build_assistant_sdk_bundle() {
    print_step "构建 Assistant SDK dist 包"

    if [[ ! -d "$ASSISTANT_SDK_DIR" ]]; then
        print_warning "Assistant SDK 目录不存在，跳过: $ASSISTANT_SDK_DIR"
        return 0
    fi
    local bun_bin="$SIDECAR_DIR/bun-bin/bun"
    if [[ "$TARGET_PLATFORM" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        bun_bin="$SIDECAR_DIR/bun-bin/bun.exe"
    fi
    run_assistant_workspace_script "$bun_bin" "build:sdk"
}

assistant_sdk_missing_files() {
    local package_dir="$1"
    python3 - "$package_dir" <<'PY'
import json
import sys
from pathlib import Path

package_dir = Path(sys.argv[1])
package_json_path = package_dir / "package.json"
if not package_json_path.exists():
    print(package_json_path)
    raise SystemExit(0)

try:
    payload = json.loads(package_json_path.read_text(encoding="utf-8"))
except Exception:
    print(package_json_path)
    raise SystemExit(0)

targets = set()

def collect(value: object) -> None:
    if isinstance(value, str):
        if value.startswith("./"):
            targets.add(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            collect(nested)
        return
    if isinstance(value, list):
        for nested in value:
            collect(nested)

for key in ("main", "types"):
    collect(payload.get(key))
collect(payload.get("exports"))

missing = [package_dir / target[2:] for target in sorted(targets) if not (package_dir / target[2:]).exists()]
for path in missing:
    print(path)
PY
}

copy_dist_ready_assistant_sdk_package() {
    local src_dir="$1"
    local dest_dir="$2"
    local missing_files=""

    missing_files="$(assistant_sdk_missing_files "$src_dir")"
    if [[ -n "$missing_files" ]]; then
        print_error "Assistant SDK dist 包不完整:"
        printf '%s\n' "$missing_files"
        exit 1
    fi

    rm -rf "$dest_dir"
    mkdir -p "$dest_dir"
    cp "$src_dir/package.json" "$dest_dir/package.json"
    if [[ -f "$src_dir/README.md" ]]; then
        cp "$src_dir/README.md" "$dest_dir/README.md"
    fi

    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete "$src_dir/dist/" "$dest_dir/dist/"
    else
        cp -R "$src_dir/dist" "$dest_dir/dist"
    fi
}

copy_assistant_sdk_bundle() {
    print_step "复制 Assistant SDK runtime bundle"

    if [[ ! -d "$ASSISTANT_SDK_DIR" ]]; then
        print_warning "Assistant SDK 目录不存在，跳过: $ASSISTANT_SDK_DIR"
        return 0
    fi

    local dest_dir="$SIDECAR_DIR/dawnchat-plugins/assistant-sdk"
    mkdir -p "$SIDECAR_DIR/dawnchat-plugins"
    rm -rf "$dest_dir"

    local package_name=""
    local package_src=""
    local package_dest=""
    for package_name in assistant-core host-orchestration-sdk; do
        package_src="$ASSISTANT_SDK_DIR/$package_name"
        package_dest="$dest_dir/$package_name"
        copy_dist_ready_assistant_sdk_package "$package_src" "$package_dest"
    done

    print_success "Assistant SDK runtime bundle 复制完成 -> $dest_dir"
}

ensure_assistant_template_dist_ready() {
    local bun_bin="$1"
    if [[ "$ASSISTANT_TEMPLATE_DIST_READY" == true ]]; then
        return 0
    fi
    run_assistant_workspace_script "$bun_bin" "build:templates"
    ASSISTANT_TEMPLATE_DIST_READY=true
}

# ============ 构建并内置 starter 模板（source + dist，不内置 node_modules） ============
prepare_builtin_desktop_template() {
    print_step "构建并内置 starter 模板 (source + dist)"

    local dest_root="$SIDECAR_DIR/dawnchat-plugins/official-plugins"
    local bun_bin="$SIDECAR_DIR/bun-bin/bun"
    if [[ "$TARGET_PLATFORM" == *"windows"* || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
        bun_bin="$SIDECAR_DIR/bun-bin/bun.exe"
    fi
    if [[ ! -x "$bun_bin" ]]; then
        print_error "缺少 bun 二进制，无法构建 starter 模板: $bun_bin"
        exit 1
    fi

    local template_id=""
    local src_dir=""
    local dest_dir=""
    local web_src=""
    local template_ids=("desktop-starter" "desktop-hello-world" "desktop-ai-assistant" "web-starter-vue" "web-ai-assistant" "mobile-starter-ionic")
    for template_id in "${template_ids[@]}"; do
        src_dir="$OFFICIAL_PLUGINS_DIR/$template_id"
        dest_dir="$dest_root/$template_id"
        if [[ ! -d "$src_dir" ]]; then
            print_warning "未找到内置模板目录，跳过: $src_dir"
            continue
        fi

        web_src="$src_dir/web-src"
        if [[ "$template_id" == "desktop-starter" ]]; then
            web_src="$src_dir/_ir/frontend/web-src"
        fi
        if [[ -f "$web_src/package.json" ]]; then
            if template_uses_assistant_sdk "$web_src/package.json"; then
                print_info "检测到 assistant-sdk workspace 依赖，改由 assistant workspace 统一构建 $template_id 前端产物"
                ensure_assistant_template_dist_ready "$bun_bin"
            else
                print_info "安装 $template_id 前端依赖..."
                (cd "$web_src" && "$bun_bin" install)
                print_info "构建 $template_id 前端产物..."
                (cd "$web_src" && "$bun_bin" run build)
            fi
        fi

        mkdir -p "$dest_root"
        rm -rf "$dest_dir"
        if command -v rsync >/dev/null 2>&1; then
            rsync -a --delete \
                --exclude "node_modules" \
                --exclude "node_modules/***" \
                --exclude "pnpm-lock.yaml" \
                "$src_dir/" "$dest_dir/"
        else
            cp -R "$src_dir" "$dest_dir"
            find "$dest_dir" -type d -name "node_modules" -prune -exec rm -rf {} +
            find "$dest_dir" -type f -name "pnpm-lock.yaml" -delete
        fi
        print_success "$template_id 已内置到 sidecar: $dest_dir"
    done
}

# ============ 复制 opencode 二进制 ============
copy_opencode_binary() {
    local platform="$1"

    print_step "复制 opencode 二进制 (Coding Agent Runtime)"

    local opencode_dir=""
    local bin_name="opencode"
    case "$platform" in
        aarch64-apple-darwin)
            opencode_dir="opencode-darwin-arm64"
            ;;
        x86_64-apple-darwin)
            opencode_dir="opencode-darwin-x64"
            ;;
        x86_64-unknown-linux-gnu)
            opencode_dir="opencode-linux-x64"
            ;;
        aarch64-unknown-linux-gnu)
            opencode_dir="opencode-linux-arm64"
            ;;
        x86_64-pc-windows-msvc)
            opencode_dir="opencode-windows-x64"
            bin_name="opencode.exe"
            ;;
        *)
            print_warning "未识别的平台，跳过 opencode 复制: $platform"
            return 0
            ;;
    esac

    local assets_dir
    assets_dir="$(resolve_runtime_asset_dir "$OPENCODE_BINARY_ASSETS_DIR" "$PROJECT_ROOT/binary/opencode-bin")"
    local src_path="$assets_dir/$opencode_dir/$bin_name"
    local dest_dir="$SIDECAR_DIR/opencode-bin"
    local dest_path="$dest_dir/$bin_name"

    if [[ ! -f "$src_path" ]]; then
        print_warning "opencode 源文件不存在: $src_path"
        return 0
    fi

    mkdir -p "$dest_dir"
    cp "$src_path" "$dest_path"
    chmod +x "$dest_path" 2>/dev/null || true
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # 避免从浏览器下载的二进制携带 quarantine，导致 Gatekeeper 拦截执行。
        if command -v xattr >/dev/null 2>&1; then
            xattr -d com.apple.quarantine "$dest_path" 2>/dev/null || true
        fi
    fi

    print_success "opencode 二进制复制完成 -> $dest_path"
}

# ============ 复制内置 OpenCode 共享规则 ============
copy_opencode_rules_default() {
    print_step "复制内置 OpenCode 共享规则 (离线兜底)"

    local src_dir="$PROJECT_ROOT/dawnchat-plugins/.opencode"
    local dest_dir="$SIDECAR_DIR/opencode-rules-default"

    if [[ ! -d "$src_dir" ]]; then
        print_warning "共享规则源目录不存在，跳过: $src_dir"
        return 0
    fi

    mkdir -p "$dest_dir"
    rm -rf "$dest_dir"/*
    cp -r "$src_dir"/* "$dest_dir/"

    print_success "内置共享规则复制完成 -> $dest_dir"
}

# ============ 创建 uv 缓存目录 ============
create_uv_cache() {
    print_step "创建 uv 缓存目录结构"
    
    # 创建 uv-cache 目录（实际缓存由运行时在用户数据目录创建）
    # 这里只是确保目录结构存在
    mkdir -p "$SIDECAR_DIR/uv-cache"
    
    print_success "uv 缓存目录创建完成"
}

# ============ 创建启动脚本 ============
create_start_scripts() {
    print_step "创建启动脚本"
    
    mkdir -p "$SIDECAR_DIR/scripts"
    
    # 确定日志级别
    local log_level="INFO"
    if [[ "$BUILD_MODE" == "debug" ]]; then
        log_level="DEBUG"
    elif [[ "$BUILD_MODE" == "release" ]]; then
        log_level="ERROR"
    fi
    
    # Unix 启动脚本
    cat > "$SIDECAR_DIR/scripts/start.sh" << SCRIPT
#!/bin/bash
SCRIPT_DIR="\$(cd "\$(dirname "\$0")" && pwd)"
BACKEND_DIR="\$(dirname "\$SCRIPT_DIR")"

export PYTHONHOME="\$BACKEND_DIR/python"
export PYTHONPATH="\$BACKEND_DIR:\$BACKEND_DIR/python/lib/python3.11/site-packages"
export PYTHONDONTWRITEBYTECODE=1
export LOG_LEVEL="$log_level"
export DAWNCHAT_RUNTIME_DISTRIBUTION="$BUILD_MODE"

exec "\$BACKEND_DIR/python/bin/python3.11" "\$BACKEND_DIR/app/main.py" "\$@"
SCRIPT
    chmod +x "$SIDECAR_DIR/scripts/start.sh"
    
    # Windows 启动脚本
    cat > "$SIDECAR_DIR/scripts/start.bat" << SCRIPT
@echo off
set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%..

set PYTHONHOME=%BACKEND_DIR%\python
set PYTHONPATH=%BACKEND_DIR%;%BACKEND_DIR%\python\Lib\site-packages
set PYTHONDONTWRITEBYTECODE=1
set LOG_LEVEL=$log_level
set DAWNCHAT_RUNTIME_DISTRIBUTION=$BUILD_MODE

"%BACKEND_DIR%\python\python.exe" "%BACKEND_DIR%\app\main.py" %*
SCRIPT
    
    print_success "启动脚本创建完成"
}

# ============ 构建前端 ============
build_frontend() {
    if [[ "$BUILD_FRONTEND" != true ]]; then
        print_info "跳过前端构建"
        return 0
    fi
    
    print_step "构建 Vue 前端"

    ensure_frontend_deps

    cd "$PROJECT_ROOT"
    pnpm --filter @dawnchat/frontend build
    
    if [[ ! -f "$FRONTEND_DIR/dist/index.html" ]]; then
        print_error "前端构建失败"
        exit 1
    fi
    
    print_success "前端构建完成"
}

calc_frontend_lock_hash() {
    local frontend_dir="$1"
    python3 - "$frontend_dir" "$PROJECT_ROOT" <<'PY'
import hashlib
import sys
from pathlib import Path

frontend_dir = Path(sys.argv[1])
project_root = Path(sys.argv[2])
files = [
    frontend_dir / "package.json",
    project_root / "package.json",
    project_root / "pnpm-lock.yaml",
    frontend_dir / "pnpm-lock.yaml",
]
h = hashlib.sha256()
for path in files:
    if path.exists():
        h.update(path.read_bytes())
print(h.hexdigest())
PY
}

ensure_frontend_deps() {
    if ! command -v pnpm &> /dev/null; then
        print_error "未找到 pnpm，请先安装 pnpm"
        exit 1
    fi

    local stamp_file="$FRONTEND_DIR/node_modules/.dawnchat-lock.sha256"
    local lock_hash
    lock_hash="$(calc_frontend_lock_hash "$FRONTEND_DIR")"
    local prev_hash=""
    if [[ -f "$stamp_file" ]]; then
        prev_hash="$(cat "$stamp_file" 2>/dev/null || true)"
    fi

    local needs_install=false
    local reason=""
    if [[ "$CLEAN_BEFORE_BUILD" == true ]]; then
        needs_install=true
        reason="--clean"
    elif [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        needs_install=true
        reason="缺少 node_modules"
    elif [[ -z "$prev_hash" || "$prev_hash" != "$lock_hash" ]]; then
        needs_install=true
        reason="前端依赖定义变更"
    fi

    if [[ "$needs_install" == true ]]; then
        print_info "安装前端依赖（$reason）..."
        cd "$PROJECT_ROOT"
        if ! pnpm install --frozen-lockfile; then
            print_warning "frozen-lockfile 安装失败，回退到普通安装（会更新 lockfile）"
            pnpm install
        fi
    fi

    if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
        mkdir -p "$FRONTEND_DIR/node_modules" 2>/dev/null || true
        echo "$lock_hash" > "$stamp_file" 2>/dev/null || true
    fi
}

# ============ 配置环境变量 ============
configure_env() {
    print_step "配置日志目录策略"
    unset DAWNCHAT_LOGS_DIR
    print_info "已禁用外部 DAWNCHAT_LOGS_DIR 覆盖"

    if [[ "$ENABLE_VERBOSE_IMPORT" == true ]]; then
        print_step "配置环境变量"
        print_info "开启 PYTHONVERBOSE=1"
        
        local lib_rs="$TAURI_DIR/src/lib.rs"
        # Uncomment the line using the marker
        if [[ "$OSTYPE" == "darwin"* ]]; then
             sed -i '' 's|// .env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|.env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|' "$lib_rs"
        else
             sed -i 's|// .env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|.env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|' "$lib_rs"
        fi
        
        # Register trap to ensure cleanup on exit
        trap revert_env EXIT
    fi
}

revert_env() {
    if [[ "$ENABLE_VERBOSE_IMPORT" == true ]]; then
        # print_info "恢复环境变量配置..."
        local lib_rs="$TAURI_DIR/src/lib.rs"
        # Re-comment the line
        if [[ "$OSTYPE" == "darwin"* ]]; then
             sed -i '' 's|^\([[:space:]]*\).env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|\1// .env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|' "$lib_rs"
        else
             sed -i 's|^\([[:space:]]*\).env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|\1// .env("PYTHONVERBOSE", "1") // BUILD_SCRIPT_TOGGLE_VERBOSE_IMPORT|' "$lib_rs"
        fi
    fi
}

# ============ 标记 PBS 打包状态 ============
set_pbs_flag() {
    local config_py="$BACKEND_DIR/app/config.py"
    if [[ -f "$config_py" ]]; then
        print_step "标记 PBS 打包状态"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|IS_PBS_APP = False  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|IS_PBS_APP = True  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|' "$config_py"
        else
            sed -i 's|IS_PBS_APP = False  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|IS_PBS_APP = True  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|' "$config_py"
        fi
    fi
}

revert_pbs_flag() {
    local config_py="$BACKEND_DIR/app/config.py"
    if [[ -f "$config_py" ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|IS_PBS_APP = True  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|IS_PBS_APP = False  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|' "$config_py"
        else
            sed -i 's|IS_PBS_APP = True  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|IS_PBS_APP = False  # BUILD_SCRIPT_TOGGLE_PBS_FLAG|' "$config_py"
        fi
    fi
}

# ============ 构建 Tauri ============
build_tauri() {
    if [[ "$BUILD_TAURI" != true ]]; then
        print_info "跳过 Tauri 构建"
        return 0
    fi
    
    print_step "构建 Tauri 应用 ($BUILD_MODE)"
    
    cd "$TAURI_DIR/.."

    if [[ "$OSTYPE" == "darwin"* ]]; then
        local resolved_xattr
        resolved_xattr="$(command -v xattr 2>/dev/null || true)"
        if [[ -x "/usr/bin/xattr" && "$resolved_xattr" != "/usr/bin/xattr" ]]; then
            print_warning "检测到非系统 xattr，已切换到系统工具链路径"
            export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
        fi
    fi
    
    local tauri_args=()
    
    if [[ "$BUILD_MODE" == "debug" ]]; then
        tauri_args+=("--debug")
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        tauri_args+=("--verbose")
    fi

    if [[ "$DMG_ONLY" == true ]]; then
        tauri_args+=("--bundles" "dmg")
    fi

    if [[ "$SIGN_MACOS" == true && -n "$MACOS_SIGNING_IDENTITY" ]]; then
        export APPLE_SIGNING_IDENTITY="$MACOS_SIGNING_IDENTITY"
    fi
    
    # 尝试完整构建
    if ! pnpm tauri build "${tauri_args[@]}"; then
        print_warning "完整构建失败，尝试只构建 app bundle..."
        if pnpm tauri build "${tauri_args[@]}" --bundles app 2>/dev/null; then
            print_success "App bundle 构建成功"
        else
            print_error "Tauri 构建失败"
            exit 1
        fi
    fi
    
    cd "$PROJECT_ROOT"
    
    print_success "Tauri 构建完成"
}

sign_macos_sidecar_binaries() {
    if [[ "$SIGN_MACOS" != true ]]; then
        return 0
    fi
    if [[ "$OSTYPE" != "darwin"* ]]; then
        return 0
    fi
    if [[ ! -d "$SIDECAR_DIR" ]]; then
        print_warning "未找到 sidecar 目录，跳过 sidecar 二进制签名"
        return 0
    fi
    local identity
    identity="$(resolve_macos_signing_identity)"
    check_macos_signing_identity "$identity"
    local entitlements_file
    entitlements_file="$(resolve_macos_entitlements_file)"
    if [[ -n "$entitlements_file" ]]; then
        print_info "sidecar 可执行文件将注入 entitlements: $entitlements_file"
    else
        print_warning "未找到 macOS entitlements 文件，sidecar 将仅使用 hardened runtime 签名"
    fi
    print_step "签名 sidecar Mach-O 二进制"
    local signed_count=0
    while IFS= read -r candidate; do
        if file "$candidate" | grep -q "Mach-O"; then
            local sign_args=(
                --force
                --sign "$identity"
                --timestamp
                --options runtime
            )
            if [[ -n "$entitlements_file" && "$candidate" != *.dylib && "$candidate" != *.so && "$candidate" != *.node ]]; then
                sign_args+=(--entitlements "$entitlements_file")
            fi
            codesign "${sign_args[@]}" "$candidate"
            signed_count=$((signed_count + 1))
        fi
    done < <(find "$SIDECAR_DIR" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" -o -name "*.node" \))
    print_success "sidecar 二进制签名完成，共处理 ${signed_count} 个文件"
}

resolve_macos_signing_identity() {
    if [[ -n "$MACOS_SIGNING_IDENTITY" ]]; then
        echo "$MACOS_SIGNING_IDENTITY"
        return
    fi
    local detected
    detected="$(security find-identity -p codesigning -v 2>/dev/null | grep "Developer ID Application:" | head -n1 | sed -E 's/.*"(.+)"/\1/')"
    echo "$detected"
}

resolve_macos_entitlements_file() {
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo ""
        return
    fi
    local candidate="$MACOS_ENTITLEMENTS_FILE"
    if [[ -f "$candidate" ]]; then
        echo "$candidate"
        return
    fi
    echo ""
}

check_macos_signing_identity() {
    local identity="$1"
    if [[ -z "$identity" ]]; then
        print_error "未找到 Developer ID Application 证书，请通过 --signing-identity 指定"
        exit 1
    fi
    if ! security find-identity -p codesigning -v | grep -F "\"$identity\"" >/dev/null 2>&1; then
        print_error "未在钥匙串中找到签名证书: $identity"
        exit 1
    fi
    print_success "签名证书就绪: $identity"
}

get_bundle_dir() {
    local bundle_dir="$TAURI_DIR/target/release/bundle"
    if [[ "$BUILD_MODE" == "debug" ]]; then
        bundle_dir="$TAURI_DIR/target/debug/bundle"
    fi
    echo "$bundle_dir"
}

find_latest_app_bundle() {
    local app_dir="$1/macos"
    if [[ ! -d "$app_dir" ]]; then
        return 0
    fi
    ls -t "$app_dir"/*.app 2>/dev/null | head -n1 || true
}

find_latest_dmg_bundle() {
    local dmg_dir="$1/dmg"
    if [[ ! -d "$dmg_dir" ]]; then
        return 0
    fi
    ls -t "$dmg_dir"/*.dmg 2>/dev/null | head -n1 || true
}

verify_macos_signature() {
    local app_path="$1"
    if [[ ! -d "$app_path" ]]; then
        print_error "未找到 .app 产物: $app_path"
        exit 1
    fi
    print_step "验证 macOS 签名"
    codesign --verify --deep --strict --verbose=2 "$app_path"
    codesign -dv --verbose=4 "$app_path" >/dev/null
    print_success "签名验证通过: $app_path"
}

notarize_and_staple_dmg() {
    local dmg_path="$1"
    if [[ ! -f "$dmg_path" ]]; then
        print_error "未找到 dmg 产物: $dmg_path"
        exit 1
    fi
    print_step "提交 Apple Notarization"
    local submit_result
    submit_result="$(xcrun notarytool submit "$dmg_path" --keychain-profile "$NOTARY_PROFILE" --output-format json)"
    local submission_id
    submission_id="$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("id",""))' <<< "$submit_result")"
    if [[ -z "$submission_id" ]]; then
        print_error "提交 notarization 失败：未获取到 Submission ID"
        exit 1
    fi
    print_info "Notarization Submission ID: $submission_id"

    local deadline_epoch
    deadline_epoch=$(( $(date +%s) + NOTARY_TIMEOUT_MINUTES * 60 ))
    local check_status=""
    local check_json=""
    while true; do
        check_json="$(xcrun notarytool info "$submission_id" --keychain-profile "$NOTARY_PROFILE" --output-format json)"
        check_status="$(python3 -c 'import json,sys;print(json.loads(sys.stdin.read()).get("status",""))' <<< "$check_json")"
        if [[ "$check_status" == "Accepted" ]]; then
            print_success "Notarization 通过: $submission_id"
            break
        fi
        if [[ "$check_status" == "Invalid" || "$check_status" == "Rejected" ]]; then
            print_error "Notarization 未通过，状态: ${check_status:-unknown}"
            xcrun notarytool log "$submission_id" --keychain-profile "$NOTARY_PROFILE" || true
            exit 1
        fi
        if [[ "$(date +%s)" -ge "$deadline_epoch" ]]; then
            print_error "Notarization 超时（${NOTARY_TIMEOUT_MINUTES} 分钟）: $submission_id"
            print_info "可手动检查状态: xcrun notarytool info $submission_id --keychain-profile $NOTARY_PROFILE"
            exit 1
        fi
        print_info "Notarization 状态: ${check_status:-In Progress}（${NOTARY_POLL_SECONDS}s 后重试）"
        sleep "$NOTARY_POLL_SECONDS"
    done

    print_step "执行 Staple"
    xcrun stapler staple "$dmg_path"
    xcrun stapler validate "$dmg_path"
    print_success "公证与 stapler 验证通过: $dmg_path"
}

assess_macos_artifacts() {
    local app_path="$1"
    local dmg_path="$2"
    local notarized="$3"
    if [[ "$notarized" != "true" ]]; then
        print_warning "当前为未公证构建，跳过 Gatekeeper 评估（spctl 会拒绝未公证包）"
        return 0
    fi
    print_step "执行 Gatekeeper 评估"
    if [[ -d "$app_path" ]]; then
        spctl --assess --type execute --verbose=4 "$app_path"
    fi
    spctl --assess --type open --context context:primary-signature --verbose=4 "$dmg_path"
    print_success "Gatekeeper 评估通过"
}

process_macos_release() {
    local platform="$1"
    if [[ "$SIGN_MACOS" != true && "$NOTARIZE_MACOS" != true ]]; then
        return 0
    fi
    if [[ "$BUILD_MODE" != "release" ]]; then
        print_error "签名与公证仅支持 release 构建"
        exit 1
    fi
    if [[ "$platform" != "aarch64-apple-darwin" && "$platform" != "x86_64-apple-darwin" ]]; then
        print_error "当前目标平台不是 macOS: $platform"
        exit 1
    fi
    local resolved_identity
    resolved_identity="$(resolve_macos_signing_identity)"
    check_macos_signing_identity "$resolved_identity"
    local bundle_dir
    bundle_dir="$(get_bundle_dir)"
    local app_path
    app_path="$(find_latest_app_bundle "$bundle_dir")"
    local dmg_path
    dmg_path="$(find_latest_dmg_bundle "$bundle_dir")"
    if [[ -z "$dmg_path" ]]; then
        print_error "未找到 dmg 产物，无法继续公证流程"
        exit 1
    fi
    if [[ -n "$app_path" ]]; then
        verify_macos_signature "$app_path"
    else
        print_warning "未找到 .app 产物，跳过 app 签名验证（dmg-only 构建场景）"
    fi
    if [[ "$NOTARIZE_MACOS" == true ]]; then
        notarize_and_staple_dmg "$dmg_path"
    fi
    assess_macos_artifacts "$app_path" "$dmg_path" "$NOTARIZE_MACOS"
}

# ============ 显示构建结果 ============
show_results() {
    print_step "构建完成"
    
    echo ""
    echo "📦 构建产物:"
    echo ""
    
    # Sidecar
    if [[ -d "$SIDECAR_DIR" ]]; then
        local sidecar_size=$(du -sh "$SIDECAR_DIR" | cut -f1)
        echo "  Python Backend: $SIDECAR_DIR ($sidecar_size)"
    fi
    
    # 前端
    if [[ -d "$FRONTEND_DIR/dist" ]]; then
        local frontend_size=$(du -sh "$FRONTEND_DIR/dist" | cut -f1)
        echo "  Vue Frontend:   $FRONTEND_DIR/dist ($frontend_size)"
    fi
    
    # Tauri 应用
    local bundle_dir="$TAURI_DIR/target"
    if [[ "$BUILD_MODE" == "debug" ]]; then
        bundle_dir="$bundle_dir/debug/bundle"
    else
        bundle_dir="$bundle_dir/release/bundle"
    fi
    
    if [[ -d "$bundle_dir" ]]; then
        echo ""
        echo "  Tauri 应用:"
        
        # macOS
        if [[ -d "$bundle_dir/macos" ]]; then
            for app in "$bundle_dir/macos"/*.app; do
                if [[ -d "$app" ]]; then
                    local app_size=$(du -sh "$app" | cut -f1)
                    echo "    - $app ($app_size)"
                fi
            done
        fi
        
        # DMG
        if [[ -d "$bundle_dir/dmg" ]]; then
            for dmg in "$bundle_dir/dmg"/*.dmg; do
                if [[ -f "$dmg" ]]; then
                    local dmg_size=$(du -sh "$dmg" | cut -f1)
                    echo "    - $dmg ($dmg_size)"
                fi
            done
        fi
    fi
    
    echo ""
}

# ============ 主函数 ============
main() {
    local start_time=$(date +%s)
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║        🚀 DawnChat 构建脚本 (Python Build Standalone)          ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # 解析参数
    parse_args "$@"
    
    # 显示配置
    local platform=$(detect_platform)
    if [[ "$BUILD_MODE" == "release" && "$USER_SET_OPTIMIZE" != true ]]; then
        ENABLE_OPTIMIZE=true
        print_info "release 模式默认启用 Python 体积优化（可通过参数显式控制）"
    fi
    print_info "构建配置:"
    echo "    模式:     $BUILD_MODE"
    echo "    平台:     $platform"
    echo "    前端:     $BUILD_FRONTEND"
    echo "    后端:     $BUILD_BACKEND"
    echo "    Tauri:    $BUILD_TAURI"
    echo "    优化:     $ENABLE_OPTIMIZE"
    echo "    MLX:      $ENABLE_MLX"
    echo "    LlamaCpp: $ENABLE_LLAMACPP"
    echo "    DMG Only: $DMG_ONLY"
    echo "    签名:     $SIGN_MACOS"
    echo "    公证:     $NOTARIZE_MACOS"
    echo "    Notary:   $NOTARY_PROFILE"
    echo "    Notary Poll(s): $NOTARY_POLL_SECONDS"
    echo "    Notary Timeout(min): $NOTARY_TIMEOUT_MINUTES"
    echo "    Kokoro:   $ENABLE_KOKORO_MODEL"
    echo ""
    
    # 检查依赖
    check_prerequisites
    
    # 确保退出时恢复 PBS 标志（包括正常结束或异常中断时执行）
    trap revert_pbs_flag EXIT
    
    # 清理（如果需要）
    if [[ "$CLEAN_BEFORE_BUILD" == true ]]; then
        clean_build
    fi
    
    # 构建后端
    if [[ "$BUILD_BACKEND" == true ]]; then
        download_pbs_python "$platform"
        install_python_deps
        set_pbs_flag
        copy_source_code
        optimize_python
        if [[ "$ENABLE_LLAMACPP" == true ]]; then
            copy_llamacpp_binary "$platform"
        else
            print_info "跳过 llama.cpp 二进制内置（默认关闭，可通过 --with-llamacpp 开启）"
        fi
        copy_tts_kokoro_model
        copy_uv_binary "$platform"
        copy_bun_binary "$platform"
        build_assistant_sdk_bundle
        copy_assistant_sdk_bundle
        prepare_builtin_desktop_template
        copy_opencode_binary "$platform"
        copy_opencode_rules_default
        create_uv_cache
        # embed_chromium
        create_start_scripts
    fi
    
    # 构建前端
    build_frontend
    
    # 构建 Tauri
    configure_env
    sign_macos_sidecar_binaries
    build_tauri
    revert_env
    process_macos_release "$platform"
    
    # 显示结果
    show_results
    
    # 计算耗时
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))
    
    echo ""
    print_success "🎉 构建完成！总耗时: ${minutes}分${seconds}秒"
    echo ""
}

# ============ 运行主函数 ============
main "$@"
