ASSISTANT_WORKSPACE_READY=false
ASSISTANT_TEMPLATE_DIST_READY=false

sync_backend_source() {
    print_step "同步后端源码"
    
    local src_dir="$BACKEND_DIR/app"
    local dest_dir="$SIDECAR_DIR/app"
    
    if [[ ! -d "$src_dir" ]]; then
        print_error "后端源目录不存在: $src_dir"
        return 1
    fi
    
    if [[ ! -d "$SIDECAR_DIR" ]]; then
        print_warning "开发运行时目录不存在: $SIDECAR_DIR"
        return 1
    fi
    
    if command -v rsync &> /dev/null; then
        rsync -av --delete --delete-excluded --force \
            --exclude '__pycache__' \
            --exclude '*.pyc' \
            --exclude '.pytest_cache' \
            "$src_dir/" "$dest_dir/"
    else
        rm -rf "$dest_dir"
        mkdir -p "$dest_dir"
        cp -R "$src_dir"/* "$dest_dir/"
        find "$dest_dir" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find "$dest_dir" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
    fi
    
    print_success "后端源码同步完成: $dest_dir"
}

get_latest_mtime() {
    local target_dir="$1"
    python3 - "$target_dir" <<'PY'
import os
import sys
from pathlib import Path

target = Path(sys.argv[1])
if not target.exists():
    print(0)
    raise SystemExit(0)
latest = 0.0
for path in target.rglob("*"):
    if path.is_file():
        latest = max(latest, path.stat().st_mtime)
print(int(latest))
PY
}

calc_web_lock_hash() {
    local web_src="$1"
    python3 - "$web_src" <<'PY'
import hashlib
import sys
from pathlib import Path

web_src = Path(sys.argv[1])
files = [web_src / "package.json", web_src / "bun.lock", web_src / "pnpm-lock.yaml", web_src / "package-lock.json", web_src / "yarn.lock"]
h = hashlib.sha256()
for path in files:
    if path.exists():
        h.update(path.read_bytes())
print(h.hexdigest())
PY
}

get_manifest_ui_type() {
    local manifest_path="$1"
    if [[ ! -f "$manifest_path" ]]; then
        return 0
    fi
    python3 - "$manifest_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    ui = data.get("ui") or {}
    print(ui.get("type", ""))
except Exception:
    print("")
PY
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
    for package_name in ("@dawnchat/assistant-app-sdk", "@dawnchat/assistant-chat-ui", "@dawnchat/assistant-core", "@dawnchat/host-orchestration-sdk"):
        if str(deps.get(package_name) or "").strip() == "workspace:*":
            raise SystemExit(0)
raise SystemExit(1)
PY
}

ensure_assistant_workspace_deps() {
    if [[ "$ASSISTANT_WORKSPACE_READY" == true ]]; then
        return 0
    fi
    local bun_bin
    bun_bin="$(resolve_bun_binary || true)"
    if [[ -z "$bun_bin" || ! -x "$bun_bin" ]]; then
        print_error "未找到 bun 二进制，无法初始化 assistant workspace"
        return 1
    fi
    if [[ ! -f "$ASSISTANT_WORKSPACE_DIR/package.json" ]]; then
        print_error "缺少 assistant workspace 配置: $ASSISTANT_WORKSPACE_DIR/package.json"
        return 1
    fi
    print_info "安装 assistant workspace 依赖..."
    if ! (cd "$ASSISTANT_WORKSPACE_DIR" && "$bun_bin" install --frozen-lockfile); then
        print_warning "bun --frozen-lockfile 失败（多为 package.json/workspaces 与 bun.lock 不一致），回退到 bun install 以更新 lockfile；请提交 dawnchat-plugins/assistant-workspace/bun.lock"
        (cd "$ASSISTANT_WORKSPACE_DIR" && "$bun_bin" install) || return 1
    fi
    ASSISTANT_WORKSPACE_READY=true
}

run_assistant_workspace_script() {
    local script_name="$1"
    local bun_bin
    bun_bin="$(resolve_bun_binary || true)"
    if [[ -z "$bun_bin" || ! -x "$bun_bin" ]]; then
        print_error "未找到 bun 二进制，无法执行 assistant workspace 脚本: $script_name"
        return 1
    fi
    ensure_assistant_workspace_deps || return 1
    print_info "执行 assistant workspace 脚本: $script_name"
    (cd "$ASSISTANT_WORKSPACE_DIR" && "$bun_bin" run "$script_name")
}

build_plugin_frontend() {
    local plugin_dir="$1"
    local web_src="$plugin_dir/web-src"
    local web_dir="$plugin_dir/web"
    local manifest_path="$plugin_dir/manifest.json"
    local ui_type
    ui_type="$(get_manifest_ui_type "$manifest_path")"

    if [[ "$ui_type" != "web" && ! -f "$web_src/package.json" ]]; then
        return 0
    fi
    if [[ ! -f "$web_src/package.json" ]]; then
        return 0
    fi

    local plugin_name
    plugin_name=$(basename "${plugin_dir%/}")
    if ! command -v pnpm &> /dev/null; then
        print_warning "pnpm 不存在，跳过插件前端构建: $plugin_name"
        return 0
    fi

    local install_failed=false
    local stamp_file="$web_src/node_modules/.dawnchat-lock.sha256"
    local lock_hash
    lock_hash="$(calc_web_lock_hash "$web_src")"
    if [[ ! -d "$web_src/node_modules" ]]; then
        if ! (cd "$web_src" && pnpm install --silent --ignore-workspace --no-frozen-lockfile); then
            install_failed=true
        fi
    else
        if [[ ! -f "$stamp_file" ]] || [[ "$(cat "$stamp_file" 2>/dev/null)" != "$lock_hash" ]]; then
            if ! (cd "$web_src" && pnpm install --silent --ignore-workspace --no-frozen-lockfile); then
                install_failed=true
            fi
        fi
    fi
    if [[ "$install_failed" == true ]]; then
        print_warning "插件前端依赖安装失败，跳过构建: $plugin_name"
        return 0
    fi
    if [[ -d "$web_src/node_modules" ]]; then
        echo "$lock_hash" > "$stamp_file" 2>/dev/null || true
    fi

    local force_build="${DAWNCHAT_PLUGIN_BUILD_FORCE:-}"
    local src_mtime
    local web_mtime
    src_mtime=$(get_latest_mtime "$web_src")
    web_mtime=$(get_latest_mtime "$web_dir")
    local need_build=false
    if [[ -n "$force_build" ]]; then
        need_build=true
    elif [[ "$web_mtime" -eq 0 ]]; then
        need_build=true
    elif [[ "$src_mtime" -gt "$web_mtime" ]]; then
        need_build=true
    fi

    if [[ "$need_build" == true ]]; then
        print_info "构建插件前端: $plugin_name"
        if ! (cd "$web_src" && pnpm exec vite build); then
            print_warning "插件前端构建失败，跳过构建产物: $plugin_name"
        fi
    else
        print_info "插件前端已是最新: $plugin_name"
    fi
}

sync_sdk() {
    print_step "同步 DawnChat SDK"
    
    local pbs_pip="$SIDECAR_DIR/python/bin/pip3.11"
    
    if [[ ! -f "$pbs_pip" ]]; then
        print_warning "PBS pip 不存在: $pbs_pip"
        print_info "尝试使用 Poetry 安装 SDK..."
        
        cd "$BACKEND_DIR"
        if command -v poetry &> /dev/null && [[ -d "$SDK_DIR" ]]; then
            poetry run pip install -e "$SDK_DIR" --quiet
            print_success "SDK 安装到 Poetry 环境"
        else
            print_warning "无法安装 SDK，跳过"
        fi
        cd "$PROJECT_ROOT"
        return 0
    fi
    
    if [[ ! -d "$SDK_DIR" ]]; then
        print_warning "SDK 目录不存在: $SDK_DIR"
        return 0
    fi
    
    print_info "使用 PBS pip 安装 SDK（可编辑模式）..."
    if "$pbs_pip" install -e "$SDK_DIR" --no-cache-dir --quiet 2>/dev/null; then
        print_success "SDK 安装完成（可编辑模式）"
    else
        print_warning "可编辑模式安装失败，尝试普通安装..."
        "$pbs_pip" install "$SDK_DIR" --no-cache-dir --quiet --force-reinstall
        print_success "SDK 安装完成"
    fi
}

assistant_sdk_needs_build() {
    local package_dir="$1"
    python3 - "$package_dir" <<'PY'
import sys
from pathlib import Path

package_dir = Path(sys.argv[1])
dist_dir = package_dir / "dist"
if not dist_dir.exists():
    raise SystemExit(0)

watch_targets = [
    package_dir / "src",
    package_dir / "package.json",
    package_dir / "tsconfig.json",
    package_dir / "vite.config.ts",
]

def latest_mtime(target: Path) -> float:
    if not target.exists():
        return 0.0
    if target.is_file():
        return target.stat().st_mtime
    latest = 0.0
    for path in target.rglob("*"):
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
    return latest

latest_source = max(latest_mtime(target) for target in watch_targets)
latest_dist = latest_mtime(dist_dir)
raise SystemExit(0 if latest_source > latest_dist else 1)
PY
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

write_sanitized_assistant_sdk_package_json() {
    local src_dir="$1"
    local dest_dir="$2"
    python3 - "$src_dir" "$dest_dir" <<'PY'
import json
import os
import sys
from pathlib import Path

src_dir = Path(sys.argv[1])
dest_dir = Path(sys.argv[2])
src_package_json_path = src_dir / "package.json"
dest_package_json_path = dest_dir / "package.json"

payload = json.loads(src_package_json_path.read_text(encoding="utf-8"))
sanitized = json.loads(json.dumps(payload))
sibling_root = src_dir.parent
internal_package_map: dict[str, str] = {}

for child in sibling_root.iterdir():
    if not child.is_dir():
        continue
    child_package_json_path = child / "package.json"
    if not child_package_json_path.exists():
        continue
    try:
        child_payload = json.loads(child_package_json_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    package_name = child_payload.get("name")
    if isinstance(package_name, str) and package_name.strip():
        internal_package_map[package_name.strip()] = child.name

sanitized.pop("scripts", None)
sanitized.pop("devDependencies", None)

runtime_dependencies = sanitized.get("dependencies")
if not isinstance(runtime_dependencies, dict):
    runtime_dependencies = {}
sanitized["dependencies"] = runtime_dependencies

for section in ("dependencies", "peerDependencies", "optionalDependencies", "devDependencies"):
    deps = payload.get(section)
    if not isinstance(deps, dict):
        continue
    for package_name in deps:
        package_dirname = internal_package_map.get(package_name)
        if not package_dirname:
            continue
        target_dir = dest_dir.parent / package_dirname
        relative_target = Path(os.path.relpath(target_dir, dest_dir))
        runtime_dependencies[package_name] = f"file:{relative_target.as_posix()}"

for section in ("peerDependencies", "optionalDependencies"):
    deps = sanitized.get(section)
    if not isinstance(deps, dict):
        continue
    for package_name in list(deps):
        if package_name in internal_package_map:
            deps.pop(package_name, None)
    if not deps:
        sanitized.pop(section, None)

errors: list[str] = []
for section in ("dependencies", "peerDependencies", "optionalDependencies"):
    deps = sanitized.get(section)
    if not isinstance(deps, dict):
        continue
    for package_name, version in deps.items():
        normalized = str(version or "").strip()
        if normalized == "workspace:*":
            errors.append(f"workspace dependency leaked: {package_name}")
        if normalized.startswith("file:") and package_name not in internal_package_map:
            errors.append(f"unsupported local dependency leaked: {package_name} -> {normalized}")

if errors:
    for error in errors:
        print(error)
    raise SystemExit(1)

dest_package_json_path.write_text(
    json.dumps(sanitized, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
PY
}

build_assistant_sdk_packages() {
    print_step "构建 Assistant SDK dist 包"

    if [[ ! -d "$ASSISTANT_SDK_DIR" ]]; then
        print_warning "Assistant SDK 目录不存在: $ASSISTANT_SDK_DIR"
        return 0
    fi

    local package_name=""
    local package_dir=""
    local needs_build=false
    for package_name in assistant-app-sdk assistant-chat-ui assistant-core host-orchestration-sdk; do
        package_dir="$ASSISTANT_SDK_DIR/$package_name"
        if [[ ! -f "$package_dir/package.json" ]]; then
            print_error "Assistant SDK 包不存在: $package_dir"
            return 1
        fi
        if assistant_sdk_needs_build "$package_dir"; then
            needs_build=true
            break
        else
            print_info "$package_name dist 已是最新，跳过构建"
        fi
    done

    if [[ "$needs_build" == true ]]; then
        run_assistant_workspace_script "build:sdk" || return 1
    fi
}

copy_dist_ready_assistant_sdk_package() {
    local src_dir="$1"
    local dest_dir="$2"
    local missing_files=""

    missing_files="$(assistant_sdk_missing_files "$src_dir")"
    if [[ -n "$missing_files" ]]; then
        print_error "Assistant SDK dist 包不完整:"
        printf '%s\n' "$missing_files"
        return 1
    fi

    rm -rf "$dest_dir"
    mkdir -p "$dest_dir"
    write_sanitized_assistant_sdk_package_json "$src_dir" "$dest_dir" || return 1
    if [[ -f "$src_dir/README.md" ]]; then
        cp "$src_dir/README.md" "$dest_dir/README.md"
    fi

    if command -v rsync &> /dev/null; then
        rsync -a --delete "$src_dir/dist/" "$dest_dir/dist/"
    else
        cp -R "$src_dir/dist" "$dest_dir/dist"
    fi
}

sync_assistant_sdk_bundle() {
    print_step "同步 Assistant SDK runtime bundle"

    if [[ ! -d "$ASSISTANT_SDK_DIR" ]]; then
        print_warning "Assistant SDK 目录不存在: $ASSISTANT_SDK_DIR"
        return 0
    fi

    local dest_root="$SIDECAR_DIR/dawnchat-plugins/assistant-sdk"
    mkdir -p "$SIDECAR_DIR/dawnchat-plugins"
    rm -rf "$dest_root"
    mkdir -p "$dest_root"

    local package_name=""
    local package_src=""
    local package_dest=""
    for package_name in assistant-app-sdk assistant-chat-ui assistant-core host-orchestration-sdk; do
        package_src="$ASSISTANT_SDK_DIR/$package_name"
        package_dest="$dest_root/$package_name"
        copy_dist_ready_assistant_sdk_package "$package_src" "$package_dest"
    done

    print_success "Assistant SDK runtime bundle 同步完成: $dest_root"
}

sync_builtin_desktop_template() {
    print_step "同步内置 starter 模板"

    local template_dest_root="$SIDECAR_DIR/dawnchat-plugins/official-plugins"
    local template_id=""
    local template_src=""
    local template_dest=""
    local web_src=""
    local bun_bin
    bun_bin="$(resolve_bun_binary || true)"
    local template_ids=("desktop-starter" "desktop-hello-world" "desktop-ai-assistant" "web-starter-vue" "web-ai-assistant" "mobile-starter-ionic" "mobile-ai-assistant")

    for template_id in "${template_ids[@]}"; do
        template_src="$PLUGINS_DIR/$template_id"
        template_dest="$template_dest_root/$template_id"
        if [[ ! -d "$template_src" ]]; then
            print_warning "未找到 starter 模板，跳过: $template_src"
            continue
        fi

        web_src="$template_src/web-src"
        if [[ "$template_id" == "desktop-starter" ]]; then
            web_src="$template_src/_ir/frontend/web-src"
        fi
        if [[ -n "$bun_bin" && -f "$web_src/package.json" ]]; then
            if template_uses_assistant_sdk "$web_src/package.json"; then
                if [[ "$ASSISTANT_TEMPLATE_DIST_READY" != true ]]; then
                    print_info "检测到 assistant-sdk workspace 依赖，改由 assistant workspace 统一构建 assistant templates"
                    run_assistant_workspace_script "build:templates" || return 1
                    ASSISTANT_TEMPLATE_DIST_READY=true
                else
                    print_info "assistant templates 前端产物已通过 assistant workspace 构建"
                fi
            else
                print_info "构建 $template_id 前端产物..."
                (cd "$web_src" && "$bun_bin" install && "$bun_bin" run build)
            fi
        fi

        mkdir -p "$template_dest_root"
        if command -v rsync &> /dev/null; then
            rsync -av --delete --delete-excluded --force \
                --exclude '__pycache__' \
                --exclude '*.pyc' \
                --exclude '.pytest_cache' \
                --exclude 'node_modules' \
                --exclude 'pnpm-lock.yaml' \
                --exclude '.dawnchat-preview' \
                "$template_src/" "$template_dest/"
        else
            rm -rf "$template_dest"
            mkdir -p "$template_dest"
            cp -R "$template_src"/* "$template_dest/"
            rm -rf "$template_dest/node_modules" \
                   "$template_dest/web-src/node_modules" \
                   "$template_dest/_ir/frontend/web-src/node_modules"
            rm -f "$template_dest/pnpm-lock.yaml" \
                  "$template_dest/web-src/pnpm-lock.yaml" \
                  "$template_dest/_ir/frontend/web-src/pnpm-lock.yaml"
        fi
        print_success "$template_id 模板同步完成: $template_dest"
    done
}

sync_tts_kokoro_model() {
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
        print_warning "未找到 Kokoro 模型目录，跳过同步"
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
    print_success "TTS Kokoro 模型同步完成: $target_dir"
}

sync_all() {
    print_step "同步开发代码到 PBS 环境"
    
    if [[ ! -d "$SIDECAR_DIR/python" ]]; then
        print_error "开发运行时 PBS 不存在: $SIDECAR_DIR/python"
        print_info "请检查 dev runtime 准备流程是否成功"
        return 1
    fi
    
    sync_backend_source || return 1
    sync_sdk || return 1
    build_assistant_sdk_packages || return 1
    sync_assistant_sdk_bundle || return 1
    sync_builtin_desktop_template || return 1
    sync_tts_kokoro_model || return 1
    
    echo ""
    print_success "🎉 代码同步完成！"
    echo ""
}
