is_truthy() {
    local value
    value="$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')"
    [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

runtime_assets_root() {
    echo "${DAWNCHAT_RUNTIME_ASSETS_DIR:-$PROJECT_ROOT/runtime-assets}"
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

use_build_sidecar_runtime() {
    is_truthy "${DAWNCHAT_DEV_USE_BUILT_SIDECAR:-}"
}

resolve_dev_runtime_root() {
    if use_build_sidecar_runtime; then
        echo "$BUILD_SIDECAR_DIR"
        return 0
    fi
    echo "$DEV_RUNTIME_DIR"
}

detect_platform_triple() {
    local os_name="$(uname -s)"
    local arch_name="$(uname -m)"
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

copy_file_if_exists() {
    local src="$1"
    local dest="$2"
    if [[ ! -f "$src" ]]; then
        return 1
    fi
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    chmod +x "$dest" 2>/dev/null || true
    remove_quarantine_if_needed "$dest"
    return 0
}

remove_quarantine_if_needed() {
    local target="$1"
    if [[ "$OSTYPE" != "darwin"* ]]; then
        return 0
    fi
    if [[ ! -e "$target" ]]; then
        return 0
    fi
    if command -v xattr >/dev/null 2>&1; then
        xattr -d com.apple.quarantine "$target" 2>/dev/null || true
    fi
    return 0
}

prepare_dev_pbs_python() {
    local platform
    platform="$(detect_platform_triple || true)"
    if [[ -z "$platform" ]]; then
        print_warning "未识别的平台，跳过 dev runtime PBS 准备"
        return 0
    fi

    local pbs_python="$SIDECAR_DIR/python/bin/python3.11"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        pbs_python="$SIDECAR_DIR/python/python.exe"
    fi
    if [[ -x "$pbs_python" ]]; then
        return 0
    fi

    local filename="cpython-${PYTHON_VERSION}+${PBS_VERSION}-${platform}-install_only.tar.gz"
    local url="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_VERSION}/${filename}"
    local cache_file="$CACHE_DIR/$filename"

    mkdir -p "$CACHE_DIR" "$SIDECAR_DIR"
    if [[ -f "$cache_file" ]]; then
        local file_size
        file_size=$(stat -f%z "$cache_file" 2>/dev/null || stat -c%s "$cache_file" 2>/dev/null || echo "0")
        if [[ "$file_size" -lt 1000000 ]]; then
            rm -f "$cache_file"
        fi
    fi
    if [[ ! -f "$cache_file" ]]; then
        print_info "下载 dev runtime PBS: $url"
        curl -L --progress-bar --fail "$url" -o "$cache_file"
    fi
    print_info "解压 PBS 到 dev runtime: $SIDECAR_DIR"
    tar -xzf "$cache_file" -C "$SIDECAR_DIR"
    chmod +x "$SIDECAR_DIR/python/bin/python3.11" 2>/dev/null || true
    chmod +x "$SIDECAR_DIR/python/bin/pip3.11" 2>/dev/null || true
}

prepare_dev_runtime_binaries() {
    local platform
    platform="$(detect_platform_triple || true)"
    if [[ -z "$platform" ]]; then
        return 0
    fi

    local assets_root
    assets_root="$(runtime_assets_root)"
    local bun_assets_dir
    bun_assets_dir="$(resolve_runtime_asset_dir "$assets_root/bun-bin" "$PROJECT_ROOT/binary/bun-bin")"
    local uv_assets_dir
    uv_assets_dir="$(resolve_runtime_asset_dir "$assets_root/uv-binary" "$BACKEND_DIR/uv-binary")"
    local opencode_assets_dir
    opencode_assets_dir="$(resolve_runtime_asset_dir "$assets_root/opencode-bin" "$PROJECT_ROOT/binary/opencode-bin")"

    local bun_dir=""
    local bun_name="bun"
    local uv_dir=""
    local opencode_dir=""
    local opencode_name="opencode"
    case "$platform" in
        aarch64-apple-darwin)
            bun_dir="bun-darwin-aarch64"
            uv_dir="uv-aarch64-apple-darwin"
            opencode_dir="opencode-darwin-arm64"
            ;;
        x86_64-apple-darwin)
            bun_dir="bun-darwin-x64"
            uv_dir="uv-x86_64-apple-darwin"
            opencode_dir="opencode-darwin-x64"
            ;;
        x86_64-unknown-linux-gnu)
            bun_dir="bun-linux-x64"
            uv_dir="uv-x86_64-unknown-linux-gnu"
            opencode_dir="opencode-linux-x64"
            ;;
        aarch64-unknown-linux-gnu)
            bun_dir="bun-linux-aarch64"
            uv_dir="uv-aarch64-unknown-linux-gnu"
            opencode_dir="opencode-linux-arm64"
            ;;
        x86_64-pc-windows-msvc)
            bun_dir="bun-windows-x64"
            bun_name="bun.exe"
            uv_dir="uv-x86_64-pc-windows-msvc"
            opencode_dir="opencode-windows-x64"
            opencode_name="opencode.exe"
            ;;
        aarch64-pc-windows-msvc)
            uv_dir="uv-aarch64-pc-windows-msvc"
            ;;
    esac

    if [[ -n "$bun_dir" ]]; then
        copy_file_if_exists \
            "$bun_assets_dir/$bun_dir/$bun_name" \
            "$SIDECAR_DIR/bun-bin/$bun_name" || true
    fi

    if [[ -n "$uv_dir" && -d "$uv_assets_dir/$uv_dir" ]]; then
        mkdir -p "$SIDECAR_DIR/uv-binary"
        cp -r "$uv_assets_dir/$uv_dir/"* "$SIDECAR_DIR/uv-binary/" 2>/dev/null || true
        chmod +x "$SIDECAR_DIR/uv-binary/uv" 2>/dev/null || true
        chmod +x "$SIDECAR_DIR/uv-binary/uvx" 2>/dev/null || true
        remove_quarantine_if_needed "$SIDECAR_DIR/uv-binary/uv"
        remove_quarantine_if_needed "$SIDECAR_DIR/uv-binary/uvx"
    fi

    if [[ -n "$opencode_dir" ]]; then
        copy_file_if_exists \
            "$opencode_assets_dir/$opencode_dir/$opencode_name" \
            "$SIDECAR_DIR/opencode-bin/$opencode_name" || true
    fi
}

prepare_dev_tts_models() {
    local model_dir_name="${KOKORO_MODEL_DIR_NAME:-kokoro-multi-lang-v1_1}"
    local source_dir=""
    local assets_root
    assets_root="$(runtime_assets_root)"
    local candidate_dirs=(
        "$assets_root/tts-models/$model_dir_name"
        "$PROJECT_ROOT/packages/backend-kernel/assets/tts/$model_dir_name"
        "$PROJECT_ROOT/download/$model_dir_name"
    )
    local candidate=""
    for candidate in "${candidate_dirs[@]}"; do
        if [[ -f "$candidate/model.onnx" ]]; then
            source_dir="$candidate"
            break
        fi
    done
    if [[ -z "$source_dir" ]]; then
        print_warning "未找到 Kokoro 模型目录，跳过 dev runtime TTS 模型准备"
        return 0
    fi

    local target_dir="$SIDECAR_DIR/tts-models/$model_dir_name"
    rm -rf "$target_dir"
    mkdir -p "$target_dir"

    if [[ -f "$source_dir/model.onnx" ]]; then
        cp "$source_dir/model.onnx" "$target_dir/model.onnx"
    else
        print_warning "Kokoro 模型缺少 onnx 文件: $source_dir"
        return 0
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
    print_success "dev runtime TTS 模型准备完成: $target_dir"
}

prepare_dev_runtime() {
    SIDECAR_DIR="$(resolve_dev_runtime_root)"
    if use_build_sidecar_runtime; then
        if [[ ! -d "$SIDECAR_DIR" ]]; then
            print_error "指定使用 build sidecar，但目录不存在: $SIDECAR_DIR"
            exit 1
        fi
        print_dev_mode "dev runtime source=build-sidecar"
        print_dev_mode "dev runtime root=$SIDECAR_DIR"
        return 0
    fi

    mkdir -p "$SIDECAR_DIR"
    prepare_dev_pbs_python
    prepare_dev_runtime_binaries
    prepare_dev_tts_models
    mkdir -p "$SIDECAR_DIR/dawnchat-plugins/official-plugins"
    print_dev_mode "dev runtime source=isolated"
    print_dev_mode "dev runtime root=$SIDECAR_DIR"
}

resolve_bun_binary() {
    local sidecar_bun="$SIDECAR_DIR/bun-bin/bun"
    if [[ -x "$sidecar_bun" ]]; then
        echo "$sidecar_bun"
        return 0
    fi
    local sidecar_bun_win="$SIDECAR_DIR/bun-bin/bun.exe"
    if [[ -x "$sidecar_bun_win" ]]; then
        echo "$sidecar_bun_win"
        return 0
    fi

    local os_name="$(uname -s)"
    local arch_name="$(uname -m)"
    local bun_subdir=""
    local bun_name="bun"
    case "$os_name" in
        Darwin)
            if [[ "$arch_name" == "arm64" ]]; then
                bun_subdir="bun-darwin-aarch64"
            else
                bun_subdir="bun-darwin-x64"
            fi
            ;;
        Linux)
            if [[ "$arch_name" == "aarch64" || "$arch_name" == "arm64" ]]; then
                bun_subdir="bun-linux-aarch64"
            else
                bun_subdir="bun-linux-x64"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            bun_subdir="bun-windows-x64"
            bun_name="bun.exe"
            ;;
    esac

    if [[ -n "$bun_subdir" ]]; then
        local assets_root
        assets_root="$(runtime_assets_root)"
        local bun_assets_dir
        bun_assets_dir="$(resolve_runtime_asset_dir "$assets_root/bun-bin" "$PROJECT_ROOT/binary/bun-bin")"
        local local_bun="$bun_assets_dir/$bun_subdir/$bun_name"
        if [[ -f "$local_bun" ]]; then
            chmod +x "$local_bun" 2>/dev/null || true
            echo "$local_bun"
            return 0
        fi
    fi
    return 1
}
