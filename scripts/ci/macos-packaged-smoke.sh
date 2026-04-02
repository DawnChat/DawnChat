#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DMG_PATH="${1:-}"
BACKEND_PORT="${DAWNCHAT_SMOKE_BACKEND_PORT:-58080}"
BACKEND_HOST="127.0.0.1"
SMOKE_TIMEOUT_SECONDS="${DAWNCHAT_SMOKE_TIMEOUT_SECONDS:-60}"

APP_MOUNT_POINT=""
APP_WORK_DIR=""
APP_PROCESS_PID=""
BACKEND_PID=""
BACKEND_LOG_PATH=""
APP_LOG_PATH=""

cleanup() {
    if [[ -n "$APP_PROCESS_PID" ]]; then
        kill "$APP_PROCESS_PID" 2>/dev/null || true
        wait "$APP_PROCESS_PID" 2>/dev/null || true
    fi
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$APP_MOUNT_POINT" ]]; then
        hdiutil detach "$APP_MOUNT_POINT" -quiet 2>/dev/null || true
    fi
    if [[ -n "$APP_WORK_DIR" && -d "$APP_WORK_DIR" ]]; then
        rm -rf "$APP_WORK_DIR"
    fi
}
trap cleanup EXIT

print_info() {
    echo "[smoke][info] $1"
}

print_error() {
    echo "[smoke][error] $1"
}

fail_with_logs() {
    local reason="$1"
    print_error "$reason"
    if [[ -n "$APP_LOG_PATH" && -f "$APP_LOG_PATH" ]]; then
        print_info "App log:"
        sed -n '1,160p' "$APP_LOG_PATH" || true
    fi
    if [[ -n "$BACKEND_LOG_PATH" && -f "$BACKEND_LOG_PATH" ]]; then
        print_info "Backend log:"
        sed -n '1,200p' "$BACKEND_LOG_PATH" || true
    fi
    exit 1
}

resolve_dmg() {
    if [[ -n "$DMG_PATH" ]]; then
        echo "$DMG_PATH"
        return 0
    fi
    local candidate
    candidate="$(ls -t "$PROJECT_ROOT/apps/desktop/src-tauri/target/release/bundle/dmg/"*.dmg 2>/dev/null | sed -n '1p')"
    if [[ -z "$candidate" ]]; then
        return 1
    fi
    echo "$candidate"
}

wait_for_http_ok() {
    local url="$1"
    local timeout="$2"
    local started
    started="$(date +%s)"
    while true; do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        local now
        now="$(date +%s)"
        if (( now - started >= timeout )); then
            return 1
        fi
        sleep 2
    done
}

DMG_FILE="$(resolve_dmg || true)"
if [[ -z "$DMG_FILE" || ! -f "$DMG_FILE" ]]; then
    fail_with_logs "未找到 DMG 产物"
fi
print_info "Using DMG: $DMG_FILE"

ATTACH_OUTPUT="$(hdiutil attach "$DMG_FILE" -nobrowse -readonly -noverify)"
APP_MOUNT_POINT="$(printf '%s\n' "$ATTACH_OUTPUT" | awk '/\/Volumes\// {print $NF}' | sed -n '1p')"
if [[ -z "$APP_MOUNT_POINT" ]]; then
    fail_with_logs "挂载 DMG 失败，未解析到 mount point"
fi
print_info "Mounted DMG: $APP_MOUNT_POINT"

APP_BUNDLE_PATH="$(ls "$APP_MOUNT_POINT"/*.app 2>/dev/null | sed -n '1p')"
if [[ -z "$APP_BUNDLE_PATH" ]]; then
    fail_with_logs "DMG 中未找到 .app 产物"
fi

APP_WORK_DIR="$(mktemp -d)"
APP_LOCAL_PATH="$APP_WORK_DIR/$(basename "$APP_BUNDLE_PATH")"
cp -R "$APP_BUNDLE_PATH" "$APP_LOCAL_PATH"
print_info "Copied app bundle: $APP_LOCAL_PATH"

APP_EXECUTABLE_NAME="$(ls "$APP_LOCAL_PATH/Contents/MacOS" 2>/dev/null | sed -n '1p')"
if [[ -z "$APP_EXECUTABLE_NAME" ]]; then
    fail_with_logs "未找到 app 主可执行文件"
fi

APP_EXECUTABLE_PATH="$APP_LOCAL_PATH/Contents/MacOS/$APP_EXECUTABLE_NAME"
APP_LOG_PATH="$APP_WORK_DIR/app-smoke.log"
"$APP_EXECUTABLE_PATH" >"$APP_LOG_PATH" 2>&1 &
APP_PROCESS_PID="$!"
sleep 6
if ! kill -0 "$APP_PROCESS_PID" 2>/dev/null; then
    fail_with_logs "App 启动失败（进程未存活）"
fi
kill "$APP_PROCESS_PID" 2>/dev/null || true
wait "$APP_PROCESS_PID" 2>/dev/null || true
APP_PROCESS_PID=""
print_info "App launch smoke passed"

SIDECAR_DIR="$APP_LOCAL_PATH/Contents/Resources/sidecars/dawnchat-backend"
PYTHON_BIN="$SIDECAR_DIR/python/bin/python3.11"
MAIN_SCRIPT="$SIDECAR_DIR/app/main.py"
if [[ ! -x "$PYTHON_BIN" || ! -f "$MAIN_SCRIPT" ]]; then
    fail_with_logs "Sidecar 运行时不完整（python/main.py 缺失）"
fi

BACKEND_LOG_PATH="$APP_WORK_DIR/backend-smoke.log"
PYTHONHOME="$SIDECAR_DIR/python" \
PYTHONPATH="$SIDECAR_DIR:$SIDECAR_DIR/app:$SIDECAR_DIR/python/lib/python3.11/site-packages" \
PYTHONDONTWRITEBYTECODE=1 \
DAWNCHAT_RUN_MODE=release \
DAWNCHAT_API_HOST="$BACKEND_HOST" \
DAWNCHAT_API_PORT="$BACKEND_PORT" \
PORT="$BACKEND_PORT" \
"$PYTHON_BIN" "$MAIN_SCRIPT" >"$BACKEND_LOG_PATH" 2>&1 &
BACKEND_PID="$!"

if ! wait_for_http_ok "http://$BACKEND_HOST:$BACKEND_PORT/frontend/health" "$SMOKE_TIMEOUT_SECONDS"; then
    fail_with_logs "backend health 检查失败"
fi
print_info "Backend health passed"

if ! wait_for_http_ok "http://$BACKEND_HOST:$BACKEND_PORT/opencode/health" "$SMOKE_TIMEOUT_SECONDS"; then
    fail_with_logs "opencode health 检查失败"
fi
print_info "OpenCode health passed"

print_info "Packaged smoke passed"
