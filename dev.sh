#!/bin/bash

# ============================================================================
# DawnChat 开发环境启动脚本
#
# 用法:
#   ./dev.sh [选项]
#
# 选项:
#   --frontend-only      仅启动前端
#   --backend-only       仅启动后端
#   --clean              清理并重新安装依赖
#   --strict-deps        严格模式：每次强制同步后端依赖
#   --sync               仅同步代码（不启动服务）
#   --no-sync            跳过同步（快速重启）
#   --show-terminal      显示 Claude Code 终端窗口（开发模式）
#   --with-mlx           安装 MLX 运行时依赖
#   --with-web-auth      额外启动 DawnChatWeb，并将桌面登录桥切到本地 5174
#   --check-web-auth-flow 校验本地 Web 登录桥联调关键地址与参数
#   --mirror <url>       指定 PyPI 镜像地址
#   --cn-mirror          使用国内镜像 (清华源) 加速下载
#   --verbose            详细输出
#   --help               显示帮助信息
#
# 功能:
#   1. 检查并清理端口占用（8000, 8080）
#   2. 设置开发环境变量
#   3. 同步代码到 PBS 环境:
#      - 后端源码: packages/backend-kernel/app → sidecar/app
#      - 官方插件: dawnchat-plugins/official-plugins → sidecar/official-plugins
#      - Python SDK: dawnchat-plugins/sdk → PBS site-packages（可编辑模式）
#      - Assistant SDK: dawnchat-plugins/assistant-sdk → sidecar/dawnchat-plugins/assistant-sdk
#   4. 启动 Python 后端（优先使用 PBS，回退到系统 Python）
#   5. 启动 Vue 开发服务器
#
# 热更新:
#   - 后端代码: 修改 packages/backend-kernel/app 后自动重载
#   - 前端代码: 修改 apps/frontend/src 后自动热更新
#   - 插件代码: 修改 dawnchat-plugins/official-plugins 后需要运行 ./dev.sh --sync
#   - Python SDK 代码: 可编辑模式安装，修改后立即生效（需重启插件）
#   - Assistant SDK 代码: 运行 `./dev.sh --sync` 后同步到 sidecar runtime
#
# ============================================================================

set -e  # 遇到错误立即退出

# ============ 默认配置 ============
FRONTEND_ONLY=false
BACKEND_ONLY=false
CLEAN_INSTALL=false
STRICT_DEPS=false
VERBOSE=false
SYNC_ONLY=false
NO_SYNC=false
PYTEST_ONLY=false
PYTEST_SCOPE=""        # unit, integration, e2e-mock, e2e-live, all
PYTEST_TARGETS=()
PYTEST_COVERAGE=false
VITEST_ONLY=false
VITEST_SCOPE=""        # coverage, ui, run
VITEST_TARGETS=()
E2E_ONLY=false
E2E_MOCK_ONLY=false
API_TYPES_ONLY=false
TEST_ALL=false
PASSTHROUGH_ARGS=()
WITH_MLX=false
WITH_WEB_AUTH=false
CHECK_WEB_AUTH_FLOW=false
MLX_VERSION="${MLX_VERSION:-0.30.3}"
MLX_LM_VERSION="${MLX_LM_VERSION:-0.30.4}"
MLX_VLM_VERSION="${MLX_VLM_VERSION:-0.3.9}"
MLX_WITH_VLM="${MLX_WITH_VLM:-true}"

# 目录配置
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/packages/backend-kernel"
FRONTEND_DIR="$PROJECT_ROOT/apps/frontend"
TAURI_DIR="$PROJECT_ROOT/apps/desktop/src-tauri"
BUILD_SIDECAR_DIR="$TAURI_DIR/sidecars/dawnchat-backend"
DEV_RUNTIME_DIR="${DAWNCHAT_DEV_RUNTIME_DIR:-$PROJECT_ROOT/.dev-runtime/dawnchat-backend}"
SIDECAR_DIR="$DEV_RUNTIME_DIR"
SDK_DIR="$PROJECT_ROOT/dawnchat-plugins/sdk"
ASSISTANT_SDK_DIR="$PROJECT_ROOT/dawnchat-plugins/assistant-sdk"
ASSISTANT_WORKSPACE_DIR="$PROJECT_ROOT/dawnchat-plugins/assistant-workspace"
PLUGINS_DIR="$PROJECT_ROOT/dawnchat-plugins/official-plugins"
WEB_AUTH_DIR="$PROJECT_ROOT/DawnChatWeb"
CACHE_DIR="$PROJECT_ROOT/.cache/pbs"
PBS_VERSION="20251202"
PYTHON_VERSION="3.11.14"
KOKORO_MODEL_DIR_NAME="${KOKORO_MODEL_DIR_NAME:-kokoro-multi-lang-v1_1}"

source "$PROJECT_ROOT/scripts/dev/common.sh"
source "$PROJECT_ROOT/scripts/dev/args.sh"
source "$PROJECT_ROOT/scripts/dev/runtime.sh"
source "$PROJECT_ROOT/scripts/dev/deps.sh"
source "$PROJECT_ROOT/scripts/dev/sync.sh"
source "$PROJECT_ROOT/scripts/dev/tests.sh"
source "$PROJECT_ROOT/scripts/dev/services.sh"

# 登录桥默认配置
PROD_WEB_AUTH_BRIDGE_URL="https://dawnchat.com/desktop-auth/bridge"
LOCAL_WEB_AUTH_BRIDGE_URL="http://localhost:5174/desktop-auth/bridge"

# 端口配置
BACKEND_PORT=8000
LLAMA_PORT=8080

# PID 文件
BACKEND_PID_FILE="/tmp/dawnchat-dev-backend.pid"
FRONTEND_PID_FILE="/tmp/dawnchat-dev-frontend.pid"
WEB_AUTH_PID_FILE="/tmp/dawnchat-dev-web-auth.pid"

# ============ 帮助信息 ============
show_help() {
    cat << EOF
DawnChat 开发环境启动脚本

用法:
    $0 [选项]

选项:
    --frontend-only      仅启动前端（Vue dev server）
    --backend-only       仅启动后端（Python PBS）
    --clean              清理并重新安装依赖
    --strict-deps        严格模式：每次强制同步后端依赖（仅后端）
    --sync               仅同步代码（后端源码 + 插件 + SDK），不启动服务
    --no-sync            跳过同步步骤（快速重启已同步的代码）
    --show-terminal      显示 Claude Code 终端窗口（开发调试模式）
    --with-mlx           安装 MLX 运行时依赖
    --with-web-auth      额外启动 DawnChatWeb，并将统一登录桥切到本地 5174
    --check-web-auth-flow 校验本地 Web 登录桥联调关键地址与参数（需服务已启动）
    --pytest [scope]     运行后端测试并退出
                         scope 可选: unit, integration, e2e-mock, e2e-live, v2, v2-all, api-integration, golden, all
                         默认: 运行所有测试
                         v2-all: 运行所有 V2 测试（包括 API 集成测试）
                         api-integration: 运行 V2 API 集成测试
    --pytest-file <path> 仅运行指定后端测试文件/目录（可重复传入）
    --vitest [scope]     运行前端测试并退出
                         scope 可选: coverage, ui, run
                         默认: vitest run（单次运行）
    --vitest-file <path> 仅运行指定前端测试文件/目录（可重复传入）
    --e2e                运行 E2E 测试（Playwright）
                         自动启动后端（Test Mode）+ 前端 + 运行测试
    --e2e-mock           运行 E2E Mock 测试（Playwright + Mock）
                         不启动后端，使用 API/WebSocket Mock，更快更稳定
    --api-types          生成 OpenAPI TypeScript 类型（需要后端运行）
    --test-all           运行完整测试套件（后端 pytest + 前端 vitest + E2E）
    --coverage           生成测试覆盖率报告（与 --pytest/--vitest 一起使用）
    --mirror <url>       指定 PyPI 镜像地址
    --cn-mirror          使用国内镜像 (清华源) 加速下载
    --verbose            详细输出
    --help               显示帮助信息
    -- [args...]         将后续参数透传给测试命令（pytest/vitest/playwright）

示例:
    $0                      # 启动完整开发环境
    $0 --frontend-only      # 仅启动前端
    $0 --backend-only       # 仅启动后端
    $0 --clean              # 清理后重启
    $0 --strict-deps        # 每次强制同步后端依赖
    $0 --sync               # 仅同步代码（不启动服务）
    $0 --no-sync            # 跳过同步（快速重启）
    $0 --pytest             # 运行所有后端测试
    $0 --pytest unit        # 仅运行单元测试（无外部依赖）
    $0 --pytest integration # 运行集成测试（需要 CAO Server）
    $0 --pytest e2e-mock    # 运行 E2E Mock 测试（需要后端服务）
    $0 --pytest e2e-live    # 运行 E2E Live 测试（需要完整环境）
    $0 --pytest v2          # 运行 V2 Pipeline 测试（隔离于 V1）
    $0 --pytest v2-all      # 运行所有 V2 测试（包括 API 集成测试）
    $0 --pytest api-integration  # 运行 V2 API 集成测试
    $0 --pytest golden      # 运行 Golden Scenario 测试（核心语义验证）
    $0 --pytest-file tests/unit/agentv3
                           # 只跑 AgentV3 单元测试目录（含 conftest）
    $0 --pytest unit -- -k stream -x
                           # pytest 透传参数：按关键字筛选并失败即停
    $0 --pytest --coverage  # 运行测试并生成覆盖率报告
    $0 --vitest             # 运行前端组件测试
    $0 --vitest coverage    # 运行前端测试并生成覆盖率报告
    $0 --vitest-file src/stores/__tests__/codingAgentStore.spec.ts
                           # 只跑指定前端测试文件
    $0 --vitest run -- --reporter=verbose
                           # vitest 透传参数
    $0 --e2e                # 运行 E2E 浏览器测试（启动真实后端）
    $0 --e2e-mock           # 运行 E2E Mock 测试（使用 Mock，更快更稳定）
    $0 --test-all           # 运行完整测试套件

环境:
    - 前端: http://localhost:5173
    - 后端: http://localhost:8000
    - WebSocket: ws://localhost:8000/ws/zmp

环境变量:
    PYPI_MIRROR          PyPI 镜像地址 (优先级低于 --mirror)
    PIP_INDEX_URL        若已配置，会自动回填为 PYPI_MIRROR
    DAWNCHAT_TEST_MODE   设置为 true 启用测试模式（E2E 测试自动设置）
    DAWNCHAT_LOGS_DIR    后端日志目录（开发模式可自定义）
EOF
}

# ============ 参数解析 ============
parse_dev_args "$@"
apply_dev_arg_defaults

# 注意：trap 在 main() 中条件注册，避免 pytest 模式下误杀其他进程

# ============ 主函数 ============
main() {
    echo -e "${MAGENTA}"
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║          DawnChat Development Environment              ║"
    echo "║                   开发模式启动                          ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    if [[ "$FRONTEND_ONLY" != true && "$VITEST_ONLY" != true ]]; then
        prepare_dev_runtime
    fi

    # 仅同步模式
    if [[ "$SYNC_ONLY" == true ]]; then
        print_info "同步模式：仅执行代码同步，不执行后端依赖同步"
        sync_all
        exit 0
    fi
    
    # 设置环境变量
    setup_env

    # 参数冲突保护：一次只跑一种测试模式
    if [[ "$PYTEST_ONLY" == true && "$VITEST_ONLY" == true ]]; then
        print_error "不能同时运行 pytest 和 vitest，请拆分为两条命令执行"
        exit 1
    fi

    # pytest 模式不需要清理进程（避免杀掉正在运行的后端服务）
    if [[ "$PYTEST_ONLY" == true ]]; then
        run_backend_pytest
        exit 0
    fi
    
    # vitest 模式
    if [[ "$VITEST_ONLY" == true ]]; then
        run_frontend_vitest
        exit 0
    fi

    if [[ "$CHECK_WEB_AUTH_FLOW" == true ]]; then
        run_web_auth_flow_check
        exit 0
    fi
    
    # E2E 模式
    if [[ "$E2E_ONLY" == true ]]; then
        run_e2e_tests
        exit 0
    fi
    
    # E2E Mock 模式
    if [[ "$E2E_MOCK_ONLY" == true ]]; then
        run_e2e_mock_tests
        exit 0
    fi
    
    # API 类型生成模式
    if [[ "$API_TYPES_ONLY" == true ]]; then
        print_step "生成 OpenAPI TypeScript 类型"
        "$PROJECT_ROOT/scripts/generate-api-types.sh"
        exit 0
    fi
    
    # 完整测试套件模式
    if [[ "$TEST_ALL" == true ]]; then
        run_all_tests
        exit 0
    fi
    
    # 只有在需要启动服务时才清理残留进程
    cleanup_processes
    
    # 只有在启动服务模式下才注册 cleanup trap（避免 pytest 模式下误杀其他进程）
    trap cleanup_on_exit SIGINT SIGTERM
    
    # 同步代码（除非指定 --no-sync）
    if [[ "$NO_SYNC" != true ]] && [[ "$FRONTEND_ONLY" != true ]]; then
        sync_all || print_warning "同步失败，继续使用现有代码..."
    fi
    
    # 启动服务
    if [[ "$FRONTEND_ONLY" == true ]]; then
        start_frontend
        start_web_auth
    elif [[ "$BACKEND_ONLY" == true ]]; then
        start_backend
        start_web_auth
    else
        start_backend
        sleep 2
        start_frontend
        start_web_auth
    fi
    
    # 显示启动信息
    show_startup_info
    
    # 等待进程
    print_info "开发环境运行中，按 Ctrl+C 停止..."
    
    # 保持脚本运行
    wait
}

# 运行主函数
main "$@"
