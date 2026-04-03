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
    if [[ "$CLEAN_INSTALL" == true ]]; then
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
        (cd "$PROJECT_ROOT" && pnpm install)
    fi

    if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
        mkdir -p "$FRONTEND_DIR/node_modules" 2>/dev/null || true
        echo "$lock_hash" > "$stamp_file" 2>/dev/null || true
    fi
}

repair_pbs_python_codesign() {
    local pbs_root="$SIDECAR_DIR/python"
    if [[ "$OSTYPE" != "darwin"* ]]; then
        return 1
    fi
    if [[ ! -d "$pbs_root" ]]; then
        return 1
    fi
    if ! command -v codesign &> /dev/null; then
        print_warning "未找到 codesign，无法修复 PBS Python 签名"
        return 1
    fi

    print_warning "检测到 PBS Python 签名冲突，尝试执行开发环境自修复..."
    local candidate=""
    local signed_count=0
    local failed_count=0
    while IFS= read -r candidate; do
        if file "$candidate" | grep -q "Mach-O"; then
            if codesign --force --sign - "$candidate" >/dev/null 2>&1; then
                signed_count=$((signed_count + 1))
            else
                failed_count=$((failed_count + 1))
            fi
        fi
    done < <(find "$pbs_root" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" -o -name "*.node" \))

    if [[ $signed_count -gt 0 ]]; then
        print_info "PBS Python 已重签名文件数: $signed_count"
    fi
    if [[ $failed_count -gt 0 ]]; then
        print_warning "PBS Python 重签名失败文件数: $failed_count"
        return 1
    fi
    return 0
}

ensure_pbs_python_usable() {
    local pbs_python="$SIDECAR_DIR/python/bin/python3.11"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        pbs_python="$SIDECAR_DIR/python/python.exe"
    fi
    if [[ ! -f "$pbs_python" || ! -x "$pbs_python" ]]; then
        return 1
    fi

    local err_file
    err_file="$(mktemp 2>/dev/null || true)"
    if [[ -z "$err_file" ]]; then
        err_file="/tmp/dawnchat-pbs-python-check.$$"
    fi

    if "$pbs_python" -V >/dev/null 2>"$err_file"; then
        rm -f "$err_file" >/dev/null 2>&1 || true
        return 0
    fi

    local err_text
    err_text="$(cat "$err_file" 2>/dev/null || true)"
    rm -f "$err_file" >/dev/null 2>&1 || true

    if [[ "$OSTYPE" == "darwin"* && "$err_text" == *"different Team IDs"* ]]; then
        if repair_pbs_python_codesign && "$pbs_python" -V >/dev/null 2>&1; then
            print_success "PBS Python 签名冲突已修复"
            return 0
        fi
    fi

    print_warning "PBS Python 不可用，将回退到 Poetry 或系统 Python"
    return 1
}

get_sha256() {
    local file_path="$1"
    if command -v shasum &> /dev/null; then
        shasum -a 256 "$file_path" | cut -d ' ' -f 1
        return 0
    fi
    if command -v sha256sum &> /dev/null; then
        sha256sum "$file_path" | cut -d ' ' -f 1
        return 0
    fi
    python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$file_path"
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

ensure_poetry_lock_consistent() {
    local project_dir="$1"
    local hint_cmd="cd $project_dir && poetry lock"
    cd "$project_dir"
    if poetry_supports_lock_check; then
        if poetry check --lock >/dev/null 2>&1; then
            return 0
        fi
        print_error "检测到 pyproject.toml 与 poetry.lock 不一致"
        print_error "请先运行: $hint_cmd"
        return 1
    fi
    if poetry_supports_lock_subcommand_check; then
        if poetry lock --check >/dev/null 2>&1; then
            return 0
        fi
        print_error "检测到 pyproject.toml 与 poetry.lock 不一致"
        print_error "请先运行: $hint_cmd"
        return 1
    fi
    print_warning "当前 Poetry 不支持 lock 一致性子命令，跳过一致性命令校验"
    return 0
}

compose_backend_deps_fingerprint() {
    local lock_hash="$1"
    local profile="$2"
    local mlx_flag="$3"
    local mlx_vlm_flag="$4"
    printf "%s|%s|mlx=%s|mlx_vlm=%s" "$lock_hash" "$profile" "$mlx_flag" "$mlx_vlm_flag"
}

decide_backend_deps_action() {
    local fingerprint="$1"
    local prev_fingerprint="$2"
    local profile="$3"

    DEPS_ACTION="skip"
    DEPS_REASON="依赖指纹未变更（profile=$profile）"
    if [[ "$CLEAN_INSTALL" == true ]]; then
        DEPS_ACTION="install"
        DEPS_REASON="--clean"
        return 0
    fi
    if [[ "$STRICT_DEPS" == true ]]; then
        DEPS_ACTION="install"
        DEPS_REASON="--strict-deps"
        return 0
    fi
    if [[ -z "$prev_fingerprint" || "$prev_fingerprint" != "$fingerprint" ]]; then
        DEPS_ACTION="install"
        DEPS_REASON="后端依赖指纹变更（profile=$profile）"
        return 0
    fi
    return 0
}

ensure_pbs_python_deps() {
    local with_dev=false
    if [[ "$1" == "--with-dev" ]]; then
        with_dev=true
        shift
    fi

    local pbs_python="$SIDECAR_DIR/python/bin/python3.11"
    local pbs_pip="$SIDECAR_DIR/python/bin/pip3.11"
    local pbs_rg="$SIDECAR_DIR/python/bin/rg"

    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        pbs_python="$SIDECAR_DIR/python/python.exe"
        pbs_pip="$SIDECAR_DIR/python/Scripts/pip.exe"
        pbs_rg="$SIDECAR_DIR/python/Scripts/rg.exe"
    fi

    if [[ ! -x "$pbs_python" || ! -f "$pbs_pip" ]]; then
        return 0
    fi
    if ! ensure_pbs_python_usable; then
        return 0
    fi

    local mirror_args=()
    if [[ -n "$PYPI_MIRROR" ]]; then
        mirror_args+=("--index-url" "$PYPI_MIRROR")
    fi

    local pyproject_path="$BACKEND_DIR/pyproject.toml"
    local lock_path="$BACKEND_DIR/poetry.lock"
    local stamp_file="$SIDECAR_DIR/python/.dawnchat-poetry-lock.sha256"
    local fallback_stamp_dir="$PROJECT_ROOT/.dawnchat-cache"
    local fallback_stamp_file="$fallback_stamp_dir/.dawnchat-poetry-lock.sha256"
    local profile="runtime"
    if [[ "$with_dev" == true ]]; then
        stamp_file="$SIDECAR_DIR/python/.dawnchat-poetry-lock.dev.sha256"
        fallback_stamp_file="$fallback_stamp_dir/.dawnchat-poetry-lock.dev.sha256"
        profile="dev"
    fi
    if [[ ! -f "$pyproject_path" || ! -f "$lock_path" ]]; then
        print_error "缺少 pyproject.toml 或 poetry.lock，无法执行后端依赖同步"
        print_error "请检查 $BACKEND_DIR 目录并补齐 lock 文件"
        exit 1
    fi

    if ! command -v poetry &> /dev/null; then
        print_error "未找到 poetry，无法执行依赖导出"
        print_error "请先安装 Poetry，再运行 dev 脚本"
        exit 1
    fi

    if ! ensure_poetry_lock_consistent "$BACKEND_DIR"; then
        exit 1
    fi
    cd "$PROJECT_ROOT"

    local lock_hash
    lock_hash="$(get_sha256 "$lock_path" 2>/dev/null || true)"
    local fingerprint
    fingerprint="$(compose_backend_deps_fingerprint "$lock_hash" "$profile" "$WITH_MLX" "$MLX_WITH_VLM")"

    local prev_fingerprint=""
    if [[ -f "$stamp_file" ]]; then
        prev_fingerprint="$(cat "$stamp_file" 2>/dev/null || true)"
    elif [[ -f "$fallback_stamp_file" ]]; then
        prev_fingerprint="$(cat "$fallback_stamp_file" 2>/dev/null || true)"
    fi
    decide_backend_deps_action "$fingerprint" "$prev_fingerprint" "$profile"
    if [[ "$DEPS_ACTION" != "install" ]]; then
        print_info "跳过 PBS Python 依赖安装（$DEPS_REASON）"
        return 0
    fi
    print_info "安装 PBS Python 依赖（$DEPS_REASON）..."

    cd "$BACKEND_DIR"

    if ! poetry export --help &> /dev/null; then
        print_error "poetry export 命令不可用，请先安装 poetry-plugin-export"
        print_error "请运行: poetry self add poetry-plugin-export"
        exit 1
    fi

    print_info "导出 requirements.txt..."
    if [[ "$with_dev" == true ]]; then
        poetry export -f requirements.txt --without-hashes --with dev -o requirements.txt
    else
        poetry export -f requirements.txt --without-hashes -o requirements.txt
    fi

    if [[ -f "$PROJECT_ROOT/scripts/ensure_pbs_deps.py" ]]; then
        print_info "同步 PBS 依赖版本..."
        python3 "$PROJECT_ROOT/scripts/ensure_pbs_deps.py" "$BACKEND_DIR/poetry.lock" "requirements.txt" >/dev/null
    fi

    local mlx_specs=()
    if [[ "$WITH_MLX" == true ]]; then
        if [[ "$(uname -s)" == "Darwin" ]]; then
            mlx_specs+=("mlx>=${MLX_VERSION}" "mlx-lm>=${MLX_LM_VERSION}")
            if [[ "$(echo "$MLX_WITH_VLM" | tr '[:upper:]' '[:lower:]')" == "true" ]]; then
                mlx_specs+=("mlx-vlm>=${MLX_VLM_VERSION}")
            fi
        else
            print_warning "当前平台非 macOS，跳过 MLX 依赖安装"
        fi
    fi

    print_info "升级 pip..."
    "$pbs_pip" install --upgrade pip --quiet "${mirror_args[@]}"

    print_info "安装 Python 依赖（PBS）..."
    if [[ "$CLEAN_INSTALL" == true || "$STRICT_DEPS" == true ]]; then
        "$pbs_pip" uninstall -y opencv-python opencv-contrib-python >/dev/null 2>&1 || true
        "$pbs_pip" install --upgrade --force-reinstall -r requirements.txt --no-cache-dir --quiet "${mirror_args[@]}"
    else
        "$pbs_pip" install --upgrade -r requirements.txt --no-cache-dir --quiet "${mirror_args[@]}"
    fi

    if [[ "${#mlx_specs[@]}" -gt 0 ]]; then
        print_info "安装 MLX 依赖..."
        if [[ "$CLEAN_INSTALL" == true ]]; then
            "$pbs_pip" install --upgrade --force-reinstall --no-deps --no-cache-dir --quiet "${mlx_specs[@]}" "${mirror_args[@]}"
        else
            "$pbs_pip" install --upgrade --no-deps --no-cache-dir --quiet "${mlx_specs[@]}" "${mirror_args[@]}"
        fi
    fi

    if [[ -n "$fingerprint" ]]; then
        if ! (mkdir -p "$(dirname "$stamp_file")" 2>/dev/null && echo "$fingerprint" > "$stamp_file" 2>/dev/null); then
            mkdir -p "$fallback_stamp_dir" 2>/dev/null || true
            echo "$fingerprint" > "$fallback_stamp_file" 2>/dev/null || true
        fi
    fi

    cd "$PROJECT_ROOT"
    print_success "PBS Python 依赖安装完成"
}

ensure_poetry_runtime_deps() {
    local with_dev=false
    if [[ "$1" == "--with-dev" ]]; then
        with_dev=true
        shift
    fi

    local pyproject_path="$BACKEND_DIR/pyproject.toml"
    local lock_path="$BACKEND_DIR/poetry.lock"
    if [[ ! -f "$pyproject_path" || ! -f "$lock_path" ]]; then
        print_error "缺少 pyproject.toml 或 poetry.lock，无法执行 Poetry 依赖同步"
        print_error "请检查 $BACKEND_DIR 目录并补齐 lock 文件"
        exit 1
    fi
    if ! command -v poetry &> /dev/null; then
        print_error "未找到 poetry，无法执行 Poetry 依赖同步"
        exit 1
    fi

    if ! ensure_poetry_lock_consistent "$BACKEND_DIR"; then
        exit 1
    fi

    cd "$BACKEND_DIR"
    local install_args=("install" "--no-root" "--no-interaction")
    if [[ "$with_dev" == true ]]; then
        install_args+=("--with" "dev")
    fi
    install_args+=("--sync")
    if [[ "$STRICT_DEPS" == true ]]; then
        print_info "Poetry 严格依赖同步中（--strict-deps）..."
    else
        print_info "Poetry 依赖同步中（--sync）..."
    fi
    poetry "${install_args[@]}"
    cd "$PROJECT_ROOT"
    print_success "Poetry 依赖同步完成"
}

find_python() {
    local pbs_python="$SIDECAR_DIR/python/bin/python3.11"
    
    if [[ -f "$pbs_python" && -x "$pbs_python" ]]; then
        if ! ensure_pbs_python_usable; then
            pbs_python=""
        fi
    fi
    if [[ -n "$pbs_python" ]]; then
        echo "$pbs_python"
        return 0
    fi
    
    if command -v poetry &> /dev/null; then
        echo "poetry run python"
        return 0
    fi
    
    if command -v python3 &> /dev/null; then
        echo "python3"
        return 0
    fi
    
    return 1
}

setup_env() {
    print_step "设置开发环境变量"
    
    export DAWNCHAT_DEV_MODE=true
    export VITE_DEV_MODE=true
    local default_bridge_url="$PROD_WEB_AUTH_BRIDGE_URL"
    if [[ "$WITH_WEB_AUTH" == true ]]; then
        default_bridge_url="$LOCAL_WEB_AUTH_BRIDGE_URL"
    fi
    export VITE_DESKTOP_AUTH_BRIDGE_BASE_URL="${VITE_DESKTOP_AUTH_BRIDGE_BASE_URL:-$default_bridge_url}"
    export VITE_DESKTOP_AUTH_REDIRECT_URI="${VITE_DESKTOP_AUTH_REDIRECT_URI:-http://localhost:5173/auth/callback}"
    
    unset DAWNCHAT_PARENT_PID
    
    export DAWNCHAT_LOG_LEVEL=DEBUG
    export DAWNCHAT_RELOAD=true
    export WATCHFILES_FORCE_POLLING=true
    export DAWNCHAT_DEV_RUNTIME_ROOT="$SIDECAR_DIR"
    local loopback_no_proxy="localhost,127.0.0.1,::1"
    if [[ -n "${NO_PROXY:-}" ]]; then
        export NO_PROXY="${NO_PROXY},${loopback_no_proxy}"
    else
        export NO_PROXY="$loopback_no_proxy"
    fi
    if [[ -n "${no_proxy:-}" ]]; then
        export no_proxy="${no_proxy},${loopback_no_proxy}"
    else
        export no_proxy="$loopback_no_proxy"
    fi

    local bun_bin
    bun_bin="$(resolve_bun_binary || true)"
    if [[ -n "$bun_bin" ]]; then
        export DAWNCHAT_BUN_BIN="$bun_bin"
        print_dev_mode "DAWNCHAT_BUN_BIN=$DAWNCHAT_BUN_BIN"
    else
        print_warning "未找到 bun 二进制，插件预览模式将不可用"
    fi
    
    print_dev_mode "DAWNCHAT_DEV_MODE=true"
    print_dev_mode "VITE_DEV_MODE=true"
    print_dev_mode "VITE_DESKTOP_AUTH_BRIDGE_BASE_URL=$VITE_DESKTOP_AUTH_BRIDGE_BASE_URL"
    print_dev_mode "VITE_DESKTOP_AUTH_REDIRECT_URI=$VITE_DESKTOP_AUTH_REDIRECT_URI"
    print_dev_mode "DAWNCHAT_PARENT_PID=<未设置，跳过父进程监控>"
    print_dev_mode "DAWNCHAT_LOG_LEVEL=DEBUG"
    if [[ -n "${DAWNCHAT_LOGS_DIR:-}" ]]; then
        print_dev_mode "DAWNCHAT_LOGS_DIR=$DAWNCHAT_LOGS_DIR"
    fi
    print_dev_mode "WATCHFILES_FORCE_POLLING=true"
    print_dev_mode "DAWNCHAT_DEV_RUNTIME_ROOT=$DAWNCHAT_DEV_RUNTIME_ROOT"
    
    print_success "环境变量设置完成"
}
