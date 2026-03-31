#!/bin/bash

# DawnChat v2 跨平台一键打包脚本
# 一次性构建所有桌面端安装包
# 每个平台只打包对应的 llama.cpp 二进制文件

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# Llama.cpp 二进制版本
LLAMA_VERSION="b7204"

# 目标平台定义
declare -A PLATFORMS=(
    ["macos-arm64"]="aarch64-apple-darwin"
    ["macos-x64"]="x86_64-apple-darwin"
    ["linux-x64"]="x86_64-unknown-linux-gnu"
    ["windows-x64"]="x86_64-pc-windows-msvc"
    ["windows-arm64"]="aarch64-pc-windows-msvc"
)

# 平台对应的 llama.cpp 二进制目录
declare -A LLAMACPP_DIRS=(
    ["macos-arm64"]="llama-${LLAMA_VERSION}-bin-macos-arm64"
    ["macos-x64"]="llama-${LLAMA_VERSION}-bin-macos-x64"
    ["linux-x64"]="llama-${LLAMA_VERSION}-bin-ubuntu-x64"
    ["windows-x64"]="llama-${LLAMA_VERSION}-bin-win-cpu-x64"
    ["windows-arm64"]="llama-${LLAMA_VERSION}-bin-win-cpu-arm64"
)

# 打印函数
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_step() {
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     🚀 DawnChat v2 跨平台打包脚本 (llama.cpp 集成)          ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# 检查必要工具
check_prerequisites() {
    print_info "检查必要工具..."
    
    local missing=()
    
    command -v pnpm &> /dev/null || missing+=("pnpm")
    command -v rustc &> /dev/null || missing+=("rust")
    command -v cargo &> /dev/null || missing+=("cargo")
    
    # Poetry 检查
    if ! command -v poetry &> /dev/null; then
        # 尝试检查常见的用户安装路径
        if [ -f "$HOME/Library/Python/3.10/bin/poetry" ]; then
            export PATH="$HOME/Library/Python/3.10/bin:$PATH"
            echo "⚠️  Poetry not found in PATH, but found in user directory. Added to PATH temporarily."
        else
            missing+=("poetry")
        fi
    fi
    
    if [ ${#missing[@]} -ne 0 ]; then
        print_error "缺少必要工具: ${missing[*]}"
        exit 1
    fi
    
    # 检查 Rust 交叉编译目标
    print_info "检查 Rust 交叉编译目标..."
    local targets=$(rustup target list --installed 2>/dev/null || echo "")
    
    print_success "工具检查完成"
}

# 检查 llama.cpp 二进制目录
check_llamacpp_binaries() {
    print_info "检查 llama.cpp 二进制目录..."
    
    local llamacpp_dir="packages/backend-kernel/llamacpp"
    local missing=()
    
    for platform in "${!LLAMACPP_DIRS[@]}"; do
        local dir_name="${LLAMACPP_DIRS[$platform]}"
        if [ ! -d "${llamacpp_dir}/${dir_name}" ]; then
            missing+=("$platform: $dir_name")
        elif [ ! -d "${llamacpp_dir}/${dir_name}/bin" ]; then
            missing+=("$platform: $dir_name/bin (缺少 bin 目录)")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        print_warning "缺少以下平台的 llama.cpp 二进制目录:"
        for m in "${missing[@]}"; do
            echo "  - $m"
        done
        echo ""
        print_info "这些平台将被跳过。如需构建，请先准备对应的二进制目录。"
    else
        print_success "所有平台的 llama.cpp 二进制目录已就绪"
    fi
}

# 获取当前系统信息
get_current_platform() {
    local arch=$(uname -m)
    local os=$(uname -s)
    
    case "$os" in
        Darwin)
            if [ "$arch" == "arm64" ]; then
                echo "macos-arm64"
            else
                echo "macos-x64"
            fi
            ;;
        Linux)
            echo "linux-x64"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows-x64"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

# 清理构建产物
clean_build() {
    print_info "清理旧的构建产物..."
    
    rm -rf packages/backend-kernel/build
    rm -rf packages/backend-kernel/dist
    rm -rf apps/desktop/src-tauri/sidecars
    rm -rf apps/frontend/dist
    rm -rf apps/desktop/src-tauri/target/release/bundle
    
    print_success "清理完成"
}

# 构建 Python 后端
build_backend() {
    print_step "构建 Python 后端"
    
    cd packages/backend-kernel
    
    if command -v poetry &> /dev/null; then
        poetry run pyinstaller dawnchat-backend.spec \
            --distpath ../../apps/desktop/src-tauri/sidecars \
            --clean \
            --noconfirm
    else
        /Users/zhutao/Library/Python/3.10/bin/poetry run pyinstaller dawnchat-backend.spec \
            --distpath ../../apps/desktop/src-tauri/sidecars \
            --clean \
            --noconfirm
    fi
    
    cd ../..
    
    if [ ! -f "apps/desktop/src-tauri/sidecars/dawnchat-backend/dawnchat-backend" ]; then
        print_error "Python 后端构建失败"
        exit 1
    fi
    
    print_success "Python 后端构建完成"
}

# 构建前端
build_frontend() {
    print_step "构建 Vue 前端"
    
    pnpm --filter @dawnchat/frontend build
    
    if [ ! -f "apps/frontend/dist/index.html" ]; then
        print_error "前端构建失败"
        exit 1
    fi
    
    print_success "Vue 前端构建完成"
}

# 为特定平台准备 sidecar
prepare_sidecar_for_platform() {
    local platform=$1
    local rust_target=${PLATFORMS[$platform]}
    local llamacpp_dir_name=${LLAMACPP_DIRS[$platform]}
    
    print_info "准备 $platform ($rust_target) 的 sidecar..."
    
    local sidecar_dir="apps/desktop/src-tauri/sidecars/dawnchat-backend"
    local llamacpp_src="packages/backend-kernel/llamacpp"
    local llamacpp_dest="${sidecar_dir}/llamacpp"
    
    # 清理并重新创建 llamacpp 目录
    rm -rf "$llamacpp_dest"
    mkdir -p "$llamacpp_dest"
    
    # 复制当前平台需要的 llama.cpp 二进制目录
    if [ -d "${llamacpp_src}/${llamacpp_dir_name}" ]; then
        cp -r "${llamacpp_src}/${llamacpp_dir_name}" "$llamacpp_dest/"
        
        # 确保可执行文件有执行权限（非 Windows）
        if [[ "$platform" != windows* ]]; then
            chmod +x "${llamacpp_dest}/${llamacpp_dir_name}/bin/llama-server" 2>/dev/null || true
            chmod +x "${llamacpp_dest}/${llamacpp_dir_name}/bin/llama-cli" 2>/dev/null || true
        fi
        
        print_success "已复制: $llamacpp_dir_name"
    else
        print_warning "未找到: $llamacpp_dir_name"
        return 1
    fi
    
    # 创建平台特定的可执行文件名
    cd "$sidecar_dir"
    
    # 根据平台确定可执行文件扩展名
    local exe_suffix=""
    if [[ "$platform" == windows* ]]; then
        exe_suffix=".exe"
    fi
    
    # 复制为平台特定名称
    if [ -f "dawnchat-backend" ]; then
        cp "dawnchat-backend" "dawnchat-backend-${rust_target}${exe_suffix}"
        print_success "创建平台可执行文件: dawnchat-backend-${rust_target}${exe_suffix}"
    fi
    
    cd - > /dev/null
}

# 构建特定平台的 Tauri 应用
build_tauri_for_platform() {
    local platform=$1
    local rust_target=${PLATFORMS[$platform]}
    
    print_step "构建 Tauri 应用: $platform"
    
    # 检查是否已安装目标
    if ! rustup target list --installed | grep -q "$rust_target"; then
        print_info "安装 Rust 目标: $rust_target"
        rustup target add "$rust_target" || {
            print_warning "无法安装 $rust_target，跳过此平台"
            return 1
        }
    fi
    
    cd apps/desktop
    
    # 根据平台决定打包类型
    local bundles=""
    case "$platform" in
        macos*)
            bundles="app,dmg"
            ;;
        linux*)
            bundles="deb,appimage"
            ;;
        windows*)
            bundles="msi,nsis"
            ;;
    esac
    
    print_info "目标: $rust_target, 打包格式: $bundles"
    
    # 尝试构建
    if pnpm tauri build --target "$rust_target" --bundles "$bundles" 2>/dev/null; then
        print_success "$platform 构建成功"
    else
        # 降级尝试：只构建 app bundle
        print_warning "完整构建失败，尝试只构建应用..."
        if pnpm tauri build --target "$rust_target" --bundles app 2>/dev/null; then
            print_success "$platform 应用构建成功（跳过安装包）"
        else
            print_error "$platform 构建失败"
            cd ../..
            return 1
        fi
    fi
    
    cd ../..
}

# 构建当前平台
build_current_platform() {
    local current=$(get_current_platform)
    
    if [ "$current" == "unknown" ]; then
        print_error "无法识别当前平台"
        exit 1
    fi
    
    print_info "当前平台: $current"
    
    # 准备 sidecar
    prepare_sidecar_for_platform "$current"
    
    # 构建 Tauri
    cd apps/desktop
    
    if ! pnpm tauri build --debug --verbose; then
        print_warning "完整构建失败，尝试只构建 app bundle..."
        if pnpm tauri build --debug --bundles app 2>/dev/null; then
            print_success "App bundle 构建成功"
        else
            print_error "构建失败"
            exit 1
        fi
    fi
    
    cd ../..
}

# 构建所有平台
build_all_platforms() {
    local current=$(get_current_platform)
    local built_platforms=()
    local failed_platforms=()
    
    print_info "开始构建所有平台..."
    print_info "当前平台: $current"
    echo ""
    
    # 首先构建当前平台（可以进行原生编译）
    print_step "构建当前平台: $current"
    prepare_sidecar_for_platform "$current"
    
    if build_tauri_for_platform "$current"; then
        built_platforms+=("$current")
    else
        failed_platforms+=("$current")
    fi
    
    # 尝试构建其他平台（交叉编译）
    for platform in "${!PLATFORMS[@]}"; do
        if [ "$platform" == "$current" ]; then
            continue
        fi
        
        local llamacpp_dir_name=${LLAMACPP_DIRS[$platform]}
        
        # 检查是否有对应的 llama.cpp 二进制目录
        if [ ! -d "packages/backend-kernel/llamacpp/${llamacpp_dir_name}" ]; then
            print_warning "跳过 $platform: 缺少 ${llamacpp_dir_name}"
            continue
        fi
        
        # macOS 无法交叉编译到 Windows/Linux，Windows 无法交叉编译到 macOS
        # 只有 Linux 可以交叉编译到 Windows
        local can_cross_compile=false
        
        case "$current" in
            macos*)
                # macOS 可以编译另一个 macOS 架构
                if [[ "$platform" == macos* && "$platform" != "$current" ]]; then
                    can_cross_compile=true
                fi
                ;;
            linux*)
                # Linux 可以交叉编译到 Windows (需要 mingw)
                if [[ "$platform" == windows* ]]; then
                    can_cross_compile=true
                fi
                ;;
        esac
        
        if [ "$can_cross_compile" = false ]; then
            print_warning "跳过 $platform: 当前环境不支持交叉编译到此平台"
            continue
        fi
        
        print_step "交叉编译: $platform"
        prepare_sidecar_for_platform "$platform"
        
        if build_tauri_for_platform "$platform"; then
            built_platforms+=("$platform")
        else
            failed_platforms+=("$platform")
        fi
    done
    
    # 打印结果摘要
    echo ""
    print_step "构建结果摘要"
    
    if [ ${#built_platforms[@]} -gt 0 ]; then
        print_success "成功构建的平台:"
        for p in "${built_platforms[@]}"; do
            echo "  ✅ $p"
        done
    fi
    
    if [ ${#failed_platforms[@]} -gt 0 ]; then
        print_error "构建失败的平台:"
        for p in "${failed_platforms[@]}"; do
            echo "  ❌ $p"
        done
    fi
}

# 显示构建结果
show_results() {
    print_step "构建产物"
    
    local bundle_dir="apps/desktop/src-tauri/target"
    
    echo ""
    echo "📦 构建产物位置:"
    echo ""
    
    # 列出所有找到的构建产物
    if [ -d "$bundle_dir" ]; then
        # macOS
        find "$bundle_dir" -path "*/bundle/macos/*.app" -type d 2>/dev/null | while read app; do
            echo "  🍎 macOS App: $app"
        done
        find "$bundle_dir" -name "*.dmg" -type f 2>/dev/null | while read dmg; do
            echo "  🍎 macOS DMG: $dmg"
        done
        
        # Linux
        find "$bundle_dir" -name "*.deb" -type f 2>/dev/null | while read deb; do
            echo "  🐧 Linux DEB: $deb"
        done
        find "$bundle_dir" -name "*.AppImage" -type f 2>/dev/null | while read appimage; do
            echo "  🐧 Linux AppImage: $appimage"
        done
        
        # Windows
        find "$bundle_dir" -name "*.msi" -type f 2>/dev/null | while read msi; do
            echo "  🪟 Windows MSI: $msi"
        done
        find "$bundle_dir" -name "*.exe" -path "*/bundle/*" -type f 2>/dev/null | while read exe; do
            echo "  🪟 Windows EXE: $exe"
        done
    fi
    
    echo ""
}

# 显示帮助信息
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --current     只构建当前平台（默认）"
    echo "  --all         尝试构建所有可能的平台"
    echo "  --platform X  只构建指定平台"
    echo "  --clean       只执行清理"
    echo "  --check       只检查环境"
    echo "  --help        显示此帮助信息"
    echo ""
    echo "支持的平台:"
    for platform in "${!PLATFORMS[@]}"; do
        echo "  - $platform (${PLATFORMS[$platform]})"
    done
    echo ""
    echo "示例:"
    echo "  $0                    # 构建当前平台"
    echo "  $0 --all              # 构建所有可能的平台"
    echo "  $0 --platform macos-arm64  # 只构建 macOS ARM64"
}

# 主函数
main() {
    local mode="current"
    local target_platform=""
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --current)
                mode="current"
                shift
                ;;
            --all)
                mode="all"
                shift
                ;;
            --platform)
                mode="single"
                target_platform="$2"
                shift 2
                ;;
            --clean)
                mode="clean"
                shift
                ;;
            --check)
                mode="check"
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
    
    print_header
    
    local start_time=$(date +%s)
    
    # 检查环境
    check_prerequisites
    check_llamacpp_binaries
    
    if [ "$mode" == "check" ]; then
        print_success "环境检查完成"
        exit 0
    fi
    
    if [ "$mode" == "clean" ]; then
        clean_build
        print_success "清理完成"
        exit 0
    fi
    
    # 清理并构建
    clean_build
    build_backend
    build_frontend
    
    case "$mode" in
        current)
            build_current_platform
            ;;
        all)
            build_all_platforms
            ;;
        single)
            if [ -z "$target_platform" ]; then
                print_error "请指定目标平台"
                exit 1
            fi
            if [ -z "${PLATFORMS[$target_platform]}" ]; then
                print_error "未知平台: $target_platform"
                show_help
                exit 1
            fi
            prepare_sidecar_for_platform "$target_platform"
            build_tauri_for_platform "$target_platform"
            ;;
    esac
    
    # 计算耗时
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # 显示结果
    show_results
    
    print_success "总耗时: ${duration} 秒"
    echo ""
}

# 运行
main "$@"

