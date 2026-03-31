parse_dev_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --)
                shift
                PASSTHROUGH_ARGS=("$@")
                break
                ;;
            --frontend-only)
                FRONTEND_ONLY=true
                shift
                ;;
            --backend-only)
                BACKEND_ONLY=true
                shift
                ;;
            --show-terminal)
                export PIPELINE_SHOW_TERMINAL=true
                print_success "✅ 已启用开发模式：将显示 Claude Code 终端窗口"
                shift
                ;;
            --with-mlx)
                WITH_MLX=true
                shift
                ;;
            --with-web-auth)
                WITH_WEB_AUTH=true
                shift
                ;;
            --check-web-auth-flow)
                CHECK_WEB_AUTH_FLOW=true
                shift
                ;;
            --pytest)
                PYTEST_ONLY=true
                if [[ -n "${2:-}" && ! "$2" =~ ^-- ]]; then
                    PYTEST_SCOPE="$2"
                    shift
                fi
                shift
                ;;
            --coverage)
                PYTEST_COVERAGE=true
                shift
                ;;
            --pytest-file)
                if [[ -z "${2:-}" || "$2" =~ ^-- ]]; then
                    print_error "--pytest-file 需要一个路径参数"
                    exit 1
                fi
                PYTEST_ONLY=true
                PYTEST_TARGETS+=("$2")
                shift 2
                ;;
            --vitest)
                VITEST_ONLY=true
                if [[ -n "${2:-}" && ! "$2" =~ ^-- ]]; then
                    VITEST_SCOPE="$2"
                    shift
                fi
                shift
                ;;
            --vitest-file)
                if [[ -z "${2:-}" || "$2" =~ ^-- ]]; then
                    print_error "--vitest-file 需要一个路径参数"
                    exit 1
                fi
                VITEST_ONLY=true
                VITEST_TARGETS+=("$2")
                shift 2
                ;;
            --e2e)
                E2E_ONLY=true
                shift
                ;;
            --e2e-mock)
                E2E_MOCK_ONLY=true
                shift
                ;;
            --api-types)
                API_TYPES_ONLY=true
                shift
                ;;
            --test-all)
                TEST_ALL=true
                shift
                ;;
            --clean)
                CLEAN_INSTALL=true
                shift
                ;;
            --sync)
                SYNC_ONLY=true
                shift
                ;;
            --no-sync)
                NO_SYNC=true
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
}

apply_dev_arg_defaults() {
    if [[ "$WITH_MLX" != true ]]; then
        if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
            WITH_MLX=true
        fi
    fi

    if [[ -z "$PYPI_MIRROR" && -n "$PIP_INDEX_URL" ]]; then
        PYPI_MIRROR="$PIP_INDEX_URL"
    fi

    if [[ -z "$PYPI_MIRROR" ]]; then
        local pip_cfg=""
        if command -v python3 >/dev/null 2>&1; then
            pip_cfg="$(python3 -m pip config get global.index-url 2>/dev/null || true)"
        fi
        if [[ "$pip_cfg" =~ ^https?:// ]]; then
            PYPI_MIRROR="$pip_cfg"
        fi
    fi

    if [[ -n "$PYPI_MIRROR" ]]; then
        export PYPI_MIRROR
        print_info "PyPI 镜像已启用: $(mask_url "$PYPI_MIRROR")"
    fi
}
