#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PROJECT_ROOT/scripts/dev/common.sh"

RUNTIME_ASSETS_DIR="${DAWNCHAT_RUNTIME_ASSETS_DIR:-$PROJECT_ROOT/runtime-assets}"
DOWNLOAD_CACHE_DIR="${DAWNCHAT_RUNTIME_ASSETS_CACHE_DIR:-$PROJECT_ROOT/.cache/runtime-assets}"
KOKORO_MODEL_URL="${DAWNCHAT_TTS_KOKORO_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-int8-multi-lang-v1_1.tar.bz2}"
KOKORO_MODEL_DIR_NAME="${KOKORO_MODEL_DIR_NAME:-kokoro-multi-lang-v1_1}"
BUN_VERSION="${DAWNCHAT_BUN_VERSION:-bun-v1.3.11}"
UV_VERSION="${DAWNCHAT_UV_VERSION:-0.11.2}"
OPENCODE_VERSION="${DAWNCHAT_OPENCODE_VERSION:-v1.3.10}"
RUNTIME_ASSETS_BASE_URL="${DAWNCHAT_RUNTIME_ASSETS_BASE_URL:-}"
DAWNCHAT_BUN_BASE_URL="${DAWNCHAT_BUN_BASE_URL:-${RUNTIME_ASSETS_BASE_URL:-https://github.com/oven-sh/bun/releases/download/$BUN_VERSION}}"
DAWNCHAT_UV_BASE_URL="${DAWNCHAT_UV_BASE_URL:-${RUNTIME_ASSETS_BASE_URL:-https://github.com/astral-sh/uv/releases/download/$UV_VERSION}}"
DAWNCHAT_OPENCODE_BASE_URL="${DAWNCHAT_OPENCODE_BASE_URL:-${RUNTIME_ASSETS_BASE_URL:-https://github.com/anomalyco/opencode/releases/download/$OPENCODE_VERSION}}"
DAWNCHAT_LLAMACPP_VERSION="${DAWNCHAT_LLAMACPP_VERSION:-b7204}"
DAWNCHAT_LLAMACPP_BASE_URL="${DAWNCHAT_LLAMACPP_BASE_URL:-https://github.com/ggml-org/llama.cpp/releases/download/$DAWNCHAT_LLAMACPP_VERSION}"

DOWNLOAD_TTS=false
DOWNLOAD_BUN=false
DOWNLOAD_UV=false
DOWNLOAD_OPENCODE=false
DOWNLOAD_LLAMACPP=false
DOWNLOAD_ALL=false
TARGET_PLATFORM=""

usage() {
    cat <<EOF
用法:
  ./scripts/download-runtime-assets.sh [选项]

选项:
  --all              下载当前平台核心运行时资源（bun/uv/opencode）
  --tts              下载 Kokoro TTS 模型
  --bun              下载 Bun 二进制
  --uv               下载 uv / uvx 二进制
  --opencode         下载 OpenCode 二进制
  --llamacpp         下载 llama.cpp 二进制
  --platform <triple> 指定平台 triple
  --help             显示帮助

环境变量:
  DAWNCHAT_RUNTIME_ASSETS_DIR
  DAWNCHAT_RUNTIME_ASSETS_BASE_URL
  DAWNCHAT_BUN_VERSION
  DAWNCHAT_UV_VERSION
  DAWNCHAT_OPENCODE_VERSION
  DAWNCHAT_BUN_BASE_URL
  DAWNCHAT_UV_BASE_URL
  DAWNCHAT_OPENCODE_BASE_URL
  DAWNCHAT_LLAMACPP_BASE_URL
  DAWNCHAT_LLAMACPP_VERSION
  DAWNCHAT_TTS_KOKORO_URL

说明:
  - TTS 模型默认使用 sherpa-onnx 官方链接。
  - Bun / uv / OpenCode 默认使用各自官方 GitHub Release 稳定版。
  - 可通过 DAWNCHAT_BUN_VERSION / DAWNCHAT_UV_VERSION / DAWNCHAT_OPENCODE_VERSION 覆盖默认版本。
  - 若配置了 DAWNCHAT_RUNTIME_ASSETS_BASE_URL，则 Bun / uv / OpenCode 可统一从同一 Release 前缀下载。
  - 统一资源目录默认写入 runtime-assets/。
EOF
}

detect_platform_triple() {
    local os_name
    os_name="$(uname -s)"
    local arch_name
    arch_name="$(uname -m)"
    case "$os_name" in
        Darwin)
            if [[ "$arch_name" == "arm64" ]]; then
                echo "aarch64-apple-darwin"
            else
                echo "x86_64-apple-darwin"
            fi
            ;;
        Linux)
            if [[ "$arch_name" == "aarch64" || "$arch_name" == "arm64" ]]; then
                echo "aarch64-unknown-linux-gnu"
            else
                echo "x86_64-unknown-linux-gnu"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            if [[ "$arch_name" == "ARM64" || "$arch_name" == "aarch64" ]]; then
                echo "aarch64-pc-windows-msvc"
            else
                echo "x86_64-pc-windows-msvc"
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

platform_value() {
    if [[ -n "$TARGET_PLATFORM" ]]; then
        echo "$TARGET_PLATFORM"
        return 0
    fi
    detect_platform_triple
}

bun_dir_for_platform() {
    case "$1" in
        aarch64-apple-darwin) echo "bun-darwin-aarch64" ;;
        x86_64-apple-darwin) echo "bun-darwin-x64" ;;
        x86_64-unknown-linux-gnu) echo "bun-linux-x64" ;;
        aarch64-unknown-linux-gnu) echo "bun-linux-aarch64" ;;
        x86_64-pc-windows-msvc) echo "bun-windows-x64" ;;
        *) return 1 ;;
    esac
}

uv_dir_for_platform() {
    case "$1" in
        aarch64-apple-darwin) echo "uv-aarch64-apple-darwin" ;;
        x86_64-apple-darwin) echo "uv-x86_64-apple-darwin" ;;
        x86_64-unknown-linux-gnu) echo "uv-x86_64-unknown-linux-gnu" ;;
        aarch64-unknown-linux-gnu) echo "uv-aarch64-unknown-linux-gnu" ;;
        x86_64-pc-windows-msvc) echo "uv-x86_64-pc-windows-msvc" ;;
        aarch64-pc-windows-msvc) echo "uv-aarch64-pc-windows-msvc" ;;
        *) return 1 ;;
    esac
}

opencode_dir_for_platform() {
    case "$1" in
        aarch64-apple-darwin) echo "opencode-darwin-arm64" ;;
        x86_64-apple-darwin) echo "opencode-darwin-x64" ;;
        x86_64-unknown-linux-gnu) echo "opencode-linux-x64" ;;
        aarch64-unknown-linux-gnu) echo "opencode-linux-arm64" ;;
        x86_64-pc-windows-msvc) echo "opencode-windows-x64" ;;
        *) return 1 ;;
    esac
}

llamacpp_dir_for_platform() {
    case "$1" in
        aarch64-apple-darwin) echo "llama-b7204-bin-macos-arm64" ;;
        x86_64-apple-darwin) echo "llama-b7204-bin-macos-x64" ;;
        x86_64-unknown-linux-gnu) echo "llama-b7204-bin-ubuntu-x64" ;;
        aarch64-pc-windows-msvc) echo "llama-b7204-bin-win-cpu-arm64" ;;
        x86_64-pc-windows-msvc) echo "llama-b7204-bin-win-cpu-x64" ;;
        *) return 1 ;;
    esac
}

require_base_url() {
    local family="$1"
    local base_url="$2"
    if [[ -n "$base_url" ]]; then
        echo "$base_url"
        return 0
    fi
    print_warning "未配置 $family 下载地址，跳过。请设置对应 BASE URL 或 DAWNCHAT_RUNTIME_ASSETS_BASE_URL"
    return 1
}

download_file() {
    local url="$1"
    local output="$2"
    mkdir -p "$(dirname "$output")"
    print_info "下载 $(mask_url "$url")"
    curl -L --progress-bar --fail "$url" -o "$output"
}

extract_archive_to_dir() {
    local archive_path="$1"
    local target_dir="$2"
    local expected_dir_name="$3"
    local staging_dir="$DOWNLOAD_CACHE_DIR/.extract-$expected_dir_name"
    rm -rf "$staging_dir" "$target_dir"
    mkdir -p "$staging_dir" "$(dirname "$target_dir")"

    case "$archive_path" in
        *.tar.gz|*.tgz)
            tar -xzf "$archive_path" -C "$staging_dir"
            ;;
        *.tar.bz2)
            tar -xjf "$archive_path" -C "$staging_dir"
            ;;
        *.zip)
            unzip -q "$archive_path" -d "$staging_dir"
            ;;
        *)
            print_error "不支持的压缩格式: $archive_path"
            return 1
            ;;
    esac

    if [[ -d "$staging_dir/$expected_dir_name" ]]; then
        mv "$staging_dir/$expected_dir_name" "$target_dir"
        rm -rf "$staging_dir"
        return 0
    fi

    local dir_count
    dir_count=$(find "$staging_dir" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
    if [[ "$dir_count" == "1" ]]; then
        local only_dir
        only_dir="$(find "$staging_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
        mv "$only_dir" "$target_dir"
        rm -rf "$staging_dir"
        return 0
    fi

    mkdir -p "$target_dir"
    find "$staging_dir" -mindepth 1 -maxdepth 1 -exec mv {} "$target_dir/" \;
    rm -rf "$staging_dir"
}

download_archive_family() {
    local family="$1"
    local base_url="$2"
    local dir_name="$3"
    local archive_name="$4"
    local target_parent="$5"
    local archive_path="$DOWNLOAD_CACHE_DIR/$archive_name"
    local url="${base_url%/}/$archive_name"
    download_file "$url" "$archive_path"
    extract_archive_to_dir "$archive_path" "$target_parent/$dir_name" "$dir_name"
    print_success "$family 资源准备完成: $target_parent/$dir_name"
}

download_tts_model() {
    local archive_name
    archive_name="$(basename "$KOKORO_MODEL_URL")"
    local archive_path="$DOWNLOAD_CACHE_DIR/$archive_name"
    download_file "$KOKORO_MODEL_URL" "$archive_path"
    extract_archive_to_dir "$archive_path" "$RUNTIME_ASSETS_DIR/tts-models/$KOKORO_MODEL_DIR_NAME" "$KOKORO_MODEL_DIR_NAME"
    print_success "Kokoro TTS 模型准备完成: $RUNTIME_ASSETS_DIR/tts-models/$KOKORO_MODEL_DIR_NAME"
}

download_bun() {
    local platform
    platform="$(platform_value)"
    local dir_name
    dir_name="$(bun_dir_for_platform "$platform")" || {
        print_warning "当前平台不支持 Bun 自动下载: $platform"
        return 0
    }
    local base_url
    base_url="$(require_base_url "Bun" "$DAWNCHAT_BUN_BASE_URL")" || return 0
    download_archive_family "Bun" "$base_url" "$dir_name" "$dir_name.zip" "$RUNTIME_ASSETS_DIR/bun-bin"
}

download_uv() {
    local platform
    platform="$(platform_value)"
    local dir_name
    dir_name="$(uv_dir_for_platform "$platform")" || {
        print_warning "当前平台不支持 uv 自动下载: $platform"
        return 0
    }
    local base_url
    base_url="$(require_base_url "uv" "$DAWNCHAT_UV_BASE_URL")" || return 0
    local archive_ext="tar.gz"
    if [[ "$platform" == "x86_64-pc-windows-msvc" || "$platform" == "aarch64-pc-windows-msvc" ]]; then
        archive_ext="zip"
    fi
    download_archive_family "uv" "$base_url" "$dir_name" "$dir_name.$archive_ext" "$RUNTIME_ASSETS_DIR/uv-binary"
}

download_opencode() {
    local platform
    platform="$(platform_value)"
    local dir_name
    dir_name="$(opencode_dir_for_platform "$platform")" || {
        print_warning "当前平台不支持 OpenCode 自动下载: $platform"
        return 0
    }
    local base_url
    base_url="$(require_base_url "OpenCode" "$DAWNCHAT_OPENCODE_BASE_URL")" || return 0
    local archive_ext="tar.gz"
    if [[ "$platform" == "aarch64-apple-darwin" || "$platform" == "x86_64-apple-darwin" || "$platform" == "x86_64-pc-windows-msvc" ]]; then
        archive_ext="zip"
    fi
    download_archive_family "OpenCode" "$base_url" "$dir_name" "$dir_name.$archive_ext" "$RUNTIME_ASSETS_DIR/opencode-bin"
}

download_llamacpp() {
    local platform
    platform="$(platform_value)"
    local dir_name
    dir_name="$(llamacpp_dir_for_platform "$platform")" || {
        print_warning "当前平台不支持 llama.cpp 自动下载: $platform"
        return 0
    }
    download_archive_family "llama.cpp" "$DAWNCHAT_LLAMACPP_BASE_URL" "$dir_name" "$dir_name.zip" "$RUNTIME_ASSETS_DIR/llamacpp"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --all)
            DOWNLOAD_ALL=true
            ;;
        --tts)
            DOWNLOAD_TTS=true
            ;;
        --bun)
            DOWNLOAD_BUN=true
            ;;
        --uv)
            DOWNLOAD_UV=true
            ;;
        --opencode)
            DOWNLOAD_OPENCODE=true
            ;;
        --llamacpp)
            DOWNLOAD_LLAMACPP=true
            ;;
        --platform)
            TARGET_PLATFORM="${2:-}"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            print_error "未知参数: $1"
            usage
            exit 1
            ;;
    esac
    shift
done

if [[ "$DOWNLOAD_ALL" == false && "$DOWNLOAD_TTS" == false && "$DOWNLOAD_BUN" == false && "$DOWNLOAD_UV" == false && "$DOWNLOAD_OPENCODE" == false && "$DOWNLOAD_LLAMACPP" == false ]]; then
    DOWNLOAD_ALL=true
fi

if [[ "$DOWNLOAD_ALL" == true ]]; then
    DOWNLOAD_BUN=true
    DOWNLOAD_UV=true
    DOWNLOAD_OPENCODE=true
    # 默认最小运行集：不包含体积较大的 Kokoro/llama.cpp，
    # 如需下载请显式传入 --tts / --llamacpp。
    DOWNLOAD_TTS=false
    DOWNLOAD_LLAMACPP=false
fi

mkdir -p "$RUNTIME_ASSETS_DIR" "$DOWNLOAD_CACHE_DIR"
print_step "准备运行时资源"
print_info "资源目录: $RUNTIME_ASSETS_DIR"
if [[ -n "$TARGET_PLATFORM" ]]; then
    print_info "目标平台: $TARGET_PLATFORM"
else
    print_info "目标平台: $(platform_value)"
fi

if [[ "$DOWNLOAD_TTS" == true ]]; then
    download_tts_model
fi
if [[ "$DOWNLOAD_BUN" == true ]]; then
    download_bun
fi
if [[ "$DOWNLOAD_UV" == true ]]; then
    download_uv
fi
if [[ "$DOWNLOAD_OPENCODE" == true ]]; then
    download_opencode
fi
if [[ "$DOWNLOAD_LLAMACPP" == true ]]; then
    download_llamacpp
fi

print_success "运行时资源准备结束"
