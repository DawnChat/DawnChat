check_and_kill_port() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null || true)
    
    if [[ -n "$pids" ]]; then
        print_warning "端口 $port 被占用，正在清理..."
        for pid in $pids; do
            if [[ -n "$pid" ]]; then
                print_info "终止进程 $pid"
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
        sleep 1
        print_success "端口 $port 已清理"
    fi
}

cleanup_processes() {
    print_step "清理残留进程"
    
    if [[ -f "$BACKEND_PID_FILE" ]]; then
        local pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            print_info "终止后端进程: $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$BACKEND_PID_FILE"
    fi
    
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
        local pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            print_info "终止前端进程: $pid"
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi
    
    check_and_kill_port $BACKEND_PORT
    check_and_kill_port $LLAMA_PORT
    
    pkill -f "dawnchat-backend" 2>/dev/null || true
    pkill -f "uvicorn.*app.main:app" 2>/dev/null || true
    
    print_success "残留进程清理完成"
}

start_backend() {
    print_step "启动 Python 后端"
    
    local python_cmd=$(find_python)
    
    if [[ -z "$python_cmd" ]]; then
        print_error "找不到可用的 Python 解释器"
        exit 1
    fi

    local desktop_dir="$HOME/Desktop"
    if [[ ! -d "$desktop_dir" ]]; then
        desktop_dir="/tmp"
    fi
    local python_log_path="$desktop_dir/DawnChat_Python.log"
    if ! touch "$python_log_path" 2>/dev/null; then
        python_log_path="/tmp/DawnChat_Python.log"
        touch "$python_log_path" 2>/dev/null || true
    fi
    print_info "Python 日志文件: $python_log_path"
    
    if [[ "$python_cmd" == "poetry run python" ]]; then
        cd "$BACKEND_DIR"
        print_info "工作目录: $BACKEND_DIR"
        print_info "启动命令: poetry run uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload"

        if [[ "$WITH_MLX" == true ]]; then
            local mirror_args=()
            if [[ -n "$PYPI_MIRROR" ]]; then
                mirror_args+=("--index-url" "$PYPI_MIRROR")
            fi
            if ! poetry run python -c "import mlx_lm" >/dev/null 2>&1; then
                print_info "安装 MLX 依赖..."
                poetry run pip install "mlx==${MLX_VERSION}" "mlx-lm==${MLX_LM_VERSION}" --quiet "${mirror_args[@]}"
            fi
            if [[ "$(echo "$MLX_WITH_VLM" | tr '[:upper:]' '[:lower:]')" == "true" ]]; then
                if ! poetry run python -c "import mlx_vlm" >/dev/null 2>&1; then
                    print_info "安装 MLX VLM 依赖..."
                    poetry run pip install "mlx-vlm==${MLX_VLM_VERSION}" --quiet "${mirror_args[@]}"
                fi
            fi
        fi
        
        poetry run uvicorn app.main:app \
            --host 0.0.0.0 \
            --port $BACKEND_PORT \
            --reload \
            --log-level debug >> "$python_log_path" 2>&1 &
        
        echo $! > "$BACKEND_PID_FILE"
        
    else
        if [[ "$python_cmd" == "python3" ]]; then
            print_warning "使用系统 Python3"
        else
            print_success "使用 PBS Python: $python_cmd"
        fi

        ensure_pbs_python_deps
        
        export PYTHONPATH="$BACKEND_DIR:${PYTHONPATH:-}"
        
        export DAWNCHAT_OFFICIAL_PLUGINS_DIR="$PLUGINS_DIR"
        
        print_info "PYTHONPATH: $PYTHONPATH"
        print_info "DAWNCHAT_OFFICIAL_PLUGINS_DIR: $PLUGINS_DIR"
        print_info "工作目录: $BACKEND_DIR"
        
        cd "$BACKEND_DIR"
        
        "$python_cmd" -m uvicorn app.main:app \
            --host 0.0.0.0 \
            --port $BACKEND_PORT \
            --reload \
            --reload-dir "$BACKEND_DIR/app" \
            --log-level debug >> "$python_log_path" 2>&1 &
        
        echo $! > "$BACKEND_PID_FILE"
    fi
    
    cd "$PROJECT_ROOT"
    
    print_info "等待后端启动..."
    local max_wait=30
    local waited=0
    
    while [[ $waited -lt $max_wait ]]; do
        if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
            print_success "后端启动成功: http://localhost:$BACKEND_PORT"
            return 0
        fi
        sleep 1
        ((waited++))
        echo -n "."
    done
    echo ""
    
    print_warning "后端可能仍在启动中，请检查日志"
}

start_frontend() {
    print_step "启动 Vue 前端"
    
    cd "$FRONTEND_DIR"

    ensure_frontend_deps
    
    print_info "启动 Vite 开发服务器..."
    print_info "前端地址: http://localhost:5173"
    
    export VITE_DEV_MODE=true
    local default_bridge_url="$PROD_WEB_AUTH_BRIDGE_URL"
    if [[ "$WITH_WEB_AUTH" == true ]]; then
        default_bridge_url="$LOCAL_WEB_AUTH_BRIDGE_URL"
    fi
    export VITE_DESKTOP_AUTH_BRIDGE_BASE_URL="${VITE_DESKTOP_AUTH_BRIDGE_BASE_URL:-$default_bridge_url}"
    export VITE_DESKTOP_AUTH_REDIRECT_URI="${VITE_DESKTOP_AUTH_REDIRECT_URI:-http://localhost:5173/auth/callback}"
    
    pnpm dev &
    echo $! > "$FRONTEND_PID_FILE"
    
    cd "$PROJECT_ROOT"
    
    print_success "前端启动成功: http://localhost:5173"
}

start_web_auth() {
    if [[ "$WITH_WEB_AUTH" != true ]]; then
        return 0
    fi
    print_step "启动 DawnChatWeb 登录桥"
    cd "$WEB_AUTH_DIR"
    print_info "启动 DawnChatWeb: http://localhost:5174"
    export VITE_DESKTOP_AUTH_REDIRECT_URI="${VITE_DESKTOP_AUTH_REDIRECT_URI:-http://localhost:5173/auth/callback}"
    pnpm dev &
    echo $! > "$WEB_AUTH_PID_FILE"
    cd "$PROJECT_ROOT"
    print_success "DawnChatWeb 启动成功: http://localhost:5174"
}

show_startup_info() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}🎉 DawnChat 开发环境已启动！${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if [[ "$BACKEND_ONLY" != true ]]; then
        echo -e "  🌐 ${CYAN}前端${NC}: http://localhost:5173"
        if [[ "$WITH_WEB_AUTH" == true ]]; then
            echo -e "  🔐 ${CYAN}本地 Web 登录桥${NC}: $LOCAL_WEB_AUTH_BRIDGE_URL"
        fi
    fi
    
    if [[ "$FRONTEND_ONLY" != true ]]; then
        echo -e "  🔧 ${CYAN}后端${NC}: http://localhost:$BACKEND_PORT"
        echo -e "  📡 ${CYAN}WebSocket${NC}: ws://localhost:$BACKEND_PORT/ws/zmp"
        echo -e "  📄 ${CYAN}API 文档${NC}: http://localhost:$BACKEND_PORT/docs"
    fi
    
    echo ""
    echo -e "${YELLOW}提示:${NC}"
    echo -e "  • 开发模式已启用，Tauri 功能将使用 Mock 实现"
    echo -e "  • 登录页面提供「开发模式（免登录）」选项"
    if [[ "$WITH_WEB_AUTH" == true ]]; then
        echo -e "  • 登录桥模式: ${CYAN}本地 (--with-web-auth)${NC}"
    else
        echo -e "  • 登录桥模式: ${CYAN}线上默认 (dawnchat.com)${NC}"
    fi
    echo -e "  • 统一登录桥地址: ${CYAN}$VITE_DESKTOP_AUTH_BRIDGE_BASE_URL${NC}"
    echo -e "  • 按 ${CYAN}Ctrl+C${NC} 停止所有服务"
    echo ""
    echo -e "${YELLOW}热更新:${NC}"
    echo -e "  • 后端代码: 修改 ${CYAN}packages/backend-kernel/app/${NC} 后自动重载"
    echo -e "  • 前端代码: 修改 ${CYAN}apps/frontend/src/${NC} 后自动热更新"
    echo -e "  • 插件/SDK: 运行 ${CYAN}./dev.sh --sync${NC} 同步最新代码"
    echo ""
}

cleanup_on_exit() {
    echo ""
    print_info "正在停止服务..."
    
    if [[ -f "$BACKEND_PID_FILE" ]]; then
        local pid=$(cat "$BACKEND_PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$BACKEND_PID_FILE"
    fi
    
    if [[ -f "$FRONTEND_PID_FILE" ]]; then
        local pid=$(cat "$FRONTEND_PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi

    if [[ -f "$WEB_AUTH_PID_FILE" ]]; then
        local pid=$(cat "$WEB_AUTH_PID_FILE" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
        rm -f "$WEB_AUTH_PID_FILE"
    fi
    
    print_success "服务已停止"
    exit 0
}
