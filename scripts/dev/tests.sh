run_backend_pytest() {
    local scope="${PYTEST_SCOPE:-}"
    local test_name="后端测试"
    local has_custom_targets=false

    if [[ "${#PYTEST_TARGETS[@]}" -gt 0 ]]; then
        has_custom_targets=true
        test_name="后端定向测试"
    fi
    
    case "$scope" in
        unit)
            test_name="单元测试"
            ;;
        integration)
            test_name="集成测试"
            ;;
        e2e-mock)
            test_name="E2E Mock 测试"
            ;;
        e2e-live)
            test_name="E2E Live 测试"
            ;;
        v2)
            test_name="V2 Pipeline 测试"
            ;;
        v2-all)
            test_name="V2 全部测试（含 API 集成）"
            ;;
        api-integration)
            test_name="V2 API 集成测试"
            ;;
        golden)
            test_name="Golden Scenario 测试"
            ;;
        all|"")
            test_name="所有测试"
            ;;
        *)
            print_error "未知的测试范围: $scope"
            print_info "可用范围: unit, integration, e2e-mock, e2e-live, v2, v2-all, api-integration, golden, all"
            exit 1
            ;;
    esac
    
    print_step "运行${test_name}"

    local python_cmd
    python_cmd="$(find_python)"
    if [[ -z "$python_cmd" ]]; then
        print_error "找不到可用的 Python 解释器"
        exit 1
    fi

    if [[ "$python_cmd" != "poetry run python" && ! -d "$SIDECAR_DIR/python" ]]; then
        print_error "开发运行时 PBS 不存在: $SIDECAR_DIR/python"
        exit 1
    fi

    if [[ "$python_cmd" != "poetry run python" ]]; then
        ensure_pbs_python_deps --with-dev
    fi

    export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"

    cd "$BACKEND_DIR"
    
    local pytest_args=()

    if [[ "$has_custom_targets" == true ]]; then
        if [[ -n "$scope" && "$scope" != "all" ]]; then
            print_warning "检测到 --pytest-file，忽略 scope 路径筛选: $scope"
        fi
        pytest_args+=("${PYTEST_TARGETS[@]}")
    else
        case "$scope" in
            unit)
                pytest_args+=("tests/unit/")
                ;;
            integration)
                pytest_args+=("tests/integration/")
                print_warning "集成测试需要 CAO Server 运行"
                ;;
            e2e-mock)
                pytest_args+=("tests/e2e/mock/")
                print_warning "E2E Mock 测试需要后端服务运行"
                ;;
            e2e-live)
                pytest_args+=("tests/e2e/live/" "tests/e2e/ai/")
                print_warning "E2E Live 测试需要完整环境（后端 + CAO Server）"
                ;;
            v2)
                pytest_args+=("-m" "v2" "tests/pipeline_v2/" "tests/pipeline_v2_api/" "tests/pipeline_v2_ws/")
                print_info "运行 V2 Pipeline 测试（隔离于 V1）"
                ;;
            v2-all)
                pytest_args+=("-m" "v2 or api_integration" "tests/pipeline_v2/" "tests/pipeline_v2_api/" "tests/pipeline_v2_ws/" "tests/pipeline_v2_api_integration/")
                print_info "运行 V2 全部测试（含 API 集成测试）"
                ;;
            api-integration)
                pytest_args+=("-m" "api_integration" "tests/pipeline_v2_api_integration/")
                print_info "运行 V2 API 集成测试"
                ;;
            golden)
                pytest_args+=("-m" "golden" "tests/pipeline_v2/")
                print_info "运行 Golden Scenario 测试（核心语义验证）"
                ;;
            all|"")
                pytest_args+=("tests/")
                ;;
        esac
    fi
    
    if [[ "$PYTEST_COVERAGE" == true ]]; then
        local mirror_args=()
        if [[ -n "$PYPI_MIRROR" ]]; then
            mirror_args+=("--index-url" "$PYPI_MIRROR")
        fi

        if [[ "$python_cmd" == "poetry run python" ]]; then
            if ! poetry run python -c "import pytest_cov" >/dev/null 2>&1; then
                print_warning "pytest-cov 未安装，正在安装..."
                poetry run pip install --upgrade pytest-cov --quiet "${mirror_args[@]}"
            fi
        else
            if ! "$python_cmd" -c "import pytest_cov" >/dev/null 2>&1; then
                print_warning "pytest-cov 未安装，正在安装..."
                if [[ -x "$SIDECAR_DIR/python/bin/pip3.11" ]]; then
                    "$SIDECAR_DIR/python/bin/pip3.11" install --upgrade pytest-cov --quiet "${mirror_args[@]}"
                else
                    "$python_cmd" -m pip install --upgrade pytest-cov --quiet "${mirror_args[@]}"
                fi
            fi
        fi

        local cov_target="app"
        if [[ "$scope" == "v2" || "$scope" == "v2-all" || "$scope" == "api-integration" || "$scope" == "golden" ]]; then
            cov_target="app/pipeline_v2"
        fi
        pytest_args+=("--cov=$cov_target" "--cov-report=html" "--cov-report=term")
        print_info "覆盖率报告将生成到: htmlcov/"
    fi
    
    if [[ "$VERBOSE" == true ]]; then
        pytest_args+=("-v")
    fi

    if [[ "${#PASSTHROUGH_ARGS[@]}" -gt 0 ]]; then
        pytest_args+=("${PASSTHROUGH_ARGS[@]}")
    fi
    
    print_info "测试路径: ${pytest_args[*]}"
    
    if [[ "$python_cmd" == "poetry run python" ]]; then
        poetry run pytest "${pytest_args[@]}"
    else
        "$python_cmd" -m pytest "${pytest_args[@]}"
    fi
    
    local exit_code=$?
    cd "$PROJECT_ROOT"
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "${test_name}通过"
    else
        print_error "${test_name}失败 (exit code: $exit_code)"
        exit $exit_code
    fi
}

run_frontend_vitest() {
    local scope="${VITEST_SCOPE:-}"
    local test_name="前端测试"
    local has_custom_targets=false

    if [[ "${#VITEST_TARGETS[@]}" -gt 0 ]]; then
        has_custom_targets=true
        test_name="前端定向测试"
    fi
    
    case "$scope" in
        coverage)
            test_name="前端测试（覆盖率）"
            ;;
        ui)
            test_name="前端测试（UI 模式）"
            ;;
        run|"")
            test_name="前端单次测试"
            ;;
        *)
            print_error "未知的测试范围: $scope"
            print_info "可用范围: coverage, ui, run"
            exit 1
            ;;
    esac
    
    print_step "运行${test_name}"
    
    cd "$FRONTEND_DIR"

    ensure_frontend_deps

    local normalized_vitest_targets=()
    if [[ "$has_custom_targets" == true ]]; then
        local target=""
        local normalized=""
        local frontend_prefix_rel="apps/frontend/"
        local frontend_prefix_abs="${FRONTEND_DIR}/"
        for target in "${VITEST_TARGETS[@]}"; do
            normalized="$target"
            if [[ "$normalized" == "$frontend_prefix_abs"* ]]; then
                normalized="${normalized#"$frontend_prefix_abs"}"
            elif [[ "$normalized" == "$frontend_prefix_rel"* ]]; then
                normalized="${normalized#"$frontend_prefix_rel"}"
            fi
            normalized_vitest_targets+=("$normalized")
        done
    fi
    
    local vitest_args=()
    case "$scope" in
        coverage)
            vitest_args=("run" "--coverage")
            print_info "覆盖率报告将生成到: coverage/"
            ;;
        ui)
            vitest_args=("--ui")
            print_info "启动 Vitest UI..."
            ;;
        run|"")
            vitest_args=("run")
            ;;
    esac

    if [[ "$has_custom_targets" == true ]]; then
        vitest_args+=("${normalized_vitest_targets[@]}")
    fi
    if [[ "${#PASSTHROUGH_ARGS[@]}" -gt 0 ]]; then
        vitest_args+=("${PASSTHROUGH_ARGS[@]}")
    fi
    if [[ "$VERBOSE" == true && "$scope" != "ui" ]]; then
        vitest_args+=("--reporter=verbose")
    fi

    print_info "测试命令: pnpm exec vitest ${vitest_args[*]}"
    pnpm exec vitest "${vitest_args[@]}"
    local exit_code=$?
    
    cd "$PROJECT_ROOT"
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "${test_name}通过"
    else
        print_error "${test_name}失败 (exit code: $exit_code)"
        exit $exit_code
    fi
}

run_web_auth_flow_check() {
    print_step "校验本地 Web 登录桥联调"

    if [[ "$WITH_WEB_AUTH" != true ]]; then
        print_error "请使用 --with-web-auth 运行检查，例如: ./dev.sh --with-web-auth --check-web-auth-flow"
        exit 1
    fi

    local bridge_url="${VITE_DESKTOP_AUTH_BRIDGE_BASE_URL:-$LOCAL_WEB_AUTH_BRIDGE_URL}"
    local callback_url="${VITE_DESKTOP_AUTH_REDIRECT_URI:-http://localhost:5173/auth/callback}"
    local frontend_url="http://localhost:5173/auth/callback"
    local web_bridge_host="http://localhost:5174/desktop-auth/bridge"

    print_info "当前桥接地址: $bridge_url"
    print_info "当前回调地址: $callback_url"

    if [[ "$callback_url" != "$frontend_url" ]]; then
      print_warning "当前回调地址不是本地默认值: $frontend_url"
    fi

    local frontend_status
    frontend_status="$(curl -sS -o /dev/null -w "%{http_code}" "$frontend_url" || true)"
    if [[ "$frontend_status" != "200" ]]; then
        print_error "前端回调地址不可用($frontend_status): $frontend_url"
        print_info "请先启动前端: ./dev.sh --frontend-only --with-web-auth"
        exit 1
    fi

    local bridge_status
    bridge_status="$(curl -sS -o /dev/null -w "%{http_code}" "$web_bridge_host" || true)"
    if [[ "$bridge_status" != "200" ]]; then
        print_error "本地 Web 登录桥不可用($bridge_status): $web_bridge_host"
        print_info "请先启动 DawnChatWeb: ./dev.sh --frontend-only --with-web-auth"
        exit 1
    fi

    local flow_status
    flow_status="$(curl -sS -o /dev/null -w "%{http_code}" --get "$bridge_url" \
      --data-urlencode "client=desktop" \
      --data-urlencode "state=dc_dev_check_state" \
      --data-urlencode "device_id=DAWNCHAT_DESKTOP_DEV_CHECK" \
      --data-urlencode "redirect_uri=$callback_url" \
      --data-urlencode "next=/app/workbench" \
      --data-urlencode "protocol_version=1" || true)"
    if [[ "$flow_status" != "200" ]]; then
        print_error "桥接参数联调检查失败($flow_status): $bridge_url"
        exit 1
    fi

    print_success "本地 Web 登录桥联调检查通过"
    echo ""
    print_info "建议手工链路验收:"
    echo "  1) 桌面端点击登录后应打开: $bridge_url"
    echo "  2) Web 未登录应先进入 /login，再返回 /desktop-auth/bridge"
    echo "  3) 回调地址应包含 ticket/state，并回到 $callback_url"
}

run_e2e_tests() {
    print_step "运行 E2E 测试 (Playwright)"
    
    print_info "清理残留进程..."
    pkill -9 -f "uvicorn.*8000" 2>/dev/null || true
    pkill -9 -f "vite.*5173" 2>/dev/null || true
    local pids_8000=$(lsof -ti :8000 2>/dev/null || true)
    local pids_5173=$(lsof -ti :5173 2>/dev/null || true)
    if [[ -n "$pids_8000" ]]; then
        echo "$pids_8000" | xargs kill -9 2>/dev/null || true
        print_info "已终止端口 8000 上的进程: $pids_8000"
    fi
    if [[ -n "$pids_5173" ]]; then
        echo "$pids_5173" | xargs kill -9 2>/dev/null || true
        print_info "已终止端口 5173 上的进程: $pids_5173"
    fi
    
    print_info "清理测试数据库..."
    local DB_PATH_USER="$HOME/Library/Application Support/DawnChat/pipeline_v2/pipeline_v2.db"
    local DB_PATH_TEST="$PROJECT_ROOT/.dawnchat-test-data/pipeline_v2/pipeline_v2.db"
    local db_paths=("$DB_PATH_USER" "$DB_PATH_TEST")
    for db_path in "${db_paths[@]}"; do
        if [[ -f "$db_path" ]]; then
            rm -f "$db_path" "$db_path-wal" "$db_path-shm" 2>/dev/null || true
            print_success "已清理测试数据库: $db_path"
        fi
    done
    
    print_info "等待端口释放..."
    local max_wait=10
    local waited=0
    while [[ $waited -lt $max_wait ]]; do
        local port_8000_busy=$(lsof -ti :8000 2>/dev/null || true)
        local port_5173_busy=$(lsof -ti :5173 2>/dev/null || true)
        if [[ -z "$port_8000_busy" && -z "$port_5173_busy" ]]; then
            print_success "端口已释放"
            break
        fi
        if [[ -n "$port_8000_busy" ]]; then
            echo "$port_8000_busy" | xargs kill -9 2>/dev/null || true
        fi
        if [[ -n "$port_5173_busy" ]]; then
            echo "$port_5173_busy" | xargs kill -9 2>/dev/null || true
        fi
        sleep 1
        waited=$((waited + 1))
        print_info "等待端口释放... ($waited/$max_wait)"
    done
    if [[ $waited -ge $max_wait ]]; then
        print_warning "端口可能仍被占用，继续尝试..."
    fi
    
    cd "$FRONTEND_DIR"

    ensure_frontend_deps
    
    if ! pnpm exec playwright --version >/dev/null 2>&1; then
        print_error "Playwright 未安装"
        print_info "请运行: cd $FRONTEND_DIR && pnpm add -D @playwright/test && pnpm exec playwright install"
        exit 1
    fi
    
    print_info "启动 E2E 测试..."
    print_info "提示: 后端将以 Test Mode 启动，使用 Mock 执行器"
    
    pnpm exec playwright test --config=e2e/playwright.config.ts "${PASSTHROUGH_ARGS[@]}"
    local exit_code=$?
    
    cd "$PROJECT_ROOT"
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "E2E 测试通过"
    else
        print_error "E2E 测试失败 (exit code: $exit_code)"
        exit $exit_code
    fi
}

run_e2e_mock_tests() {
    print_step "运行 E2E Mock 测试 (Playwright + Mock)"
    print_info "使用 API/WebSocket Mock，不启动后端服务器"
    
    cd "$FRONTEND_DIR"

    ensure_frontend_deps
    
    if ! pnpm exec playwright --version >/dev/null 2>&1; then
        print_error "Playwright 未安装"
        print_info "请运行: cd $FRONTEND_DIR && pnpm add -D @playwright/test && pnpm exec playwright install"
        exit 1
    fi
    
    if [[ ! -d "e2e/tests-mock" ]]; then
        print_error "Mock 测试目录不存在: e2e/tests-mock"
        print_info "请先创建 Mock 测试文件"
        exit 1
    fi
    
    print_info "启动 E2E Mock 测试..."
    print_info "提示: 仅启动前端开发服务器，API 和 WebSocket 由 Mock 提供"
    
    pnpm exec playwright test --config=e2e/playwright.mock.config.ts "${PASSTHROUGH_ARGS[@]}"
    local exit_code=$?
    
    cd "$PROJECT_ROOT"
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "E2E Mock 测试通过"
    else
        print_error "E2E Mock 测试失败 (exit code: $exit_code)"
        exit $exit_code
    fi
}

run_all_tests() {
    print_step "运行完整测试套件"
    
    local failed_tests=()
    
    print_info "=== 1/3 后端测试 ==="
    PYTEST_SCOPE="v2"
    if run_backend_pytest; then
        print_success "后端测试通过"
    else
        failed_tests+=("后端测试")
        print_warning "后端测试失败，继续运行其他测试..."
    fi
    
    print_info "=== 2/3 前端测试 ==="
    VITEST_SCOPE="run"
    if run_frontend_vitest; then
        print_success "前端测试通过"
    else
        failed_tests+=("前端测试")
        print_warning "前端测试失败，继续运行其他测试..."
    fi
    
    print_info "=== 3/3 E2E 测试 ==="
    if run_e2e_tests; then
        print_success "E2E 测试通过"
    else
        failed_tests+=("E2E 测试")
    fi
    
    echo ""
    print_step "测试套件汇总"
    
    if [[ ${#failed_tests[@]} -eq 0 ]]; then
        print_success "所有测试通过！"
        exit 0
    else
        print_error "以下测试失败:"
        for test in "${failed_tests[@]}"; do
            echo "  - $test"
        done
        exit 1
    fi
}
