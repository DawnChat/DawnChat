#!/usr/bin/env python3
"""
scripts/optimize_python.py
优化 PBS Python 体积，删除不需要的文件

使用方法:
    python optimize_python.py <python_dir>
"""

from pathlib import Path
import shutil
import sys

# 不需要的标准库模块
UNNECESSARY_MODULES = [
    "tkinter",      # GUI 模块，桌面应用不需要 Python 的 GUI
    "turtle",       # 绘图模块
    "turtledemo",   # turtle 示例
    "idlelib",      # IDLE 编辑器
    "lib2to3",      # Python 2 转换工具
    "ensurepip",    # pip 安装器（已经有 pip）
    "venv",         # 虚拟环境（PBS 自带）
    "distutils",    # 已废弃的打包工具
]

# 不需要的 site-packages 内容
UNNECESSARY_SITE_PACKAGES = [
    "*.dist-info",   # 包元数据（可选保留）
    "pip",           # pip 本身（构建完成后不需要）
    "setuptools",    # setuptools（构建完成后不需要）
]

METADATA_TXT_BASENAMES = {
    "entry_points.txt",
    "top_level.txt",
    "requires.txt",
    "dependency_links.txt",
}


def get_dir_size(path: Path) -> int:
    """获取目录大小（字节）"""
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def remove_safely(path: Path, verbose: bool = False) -> int:
    """安全删除文件或目录，返回删除的字节数"""
    if not path.exists():
        return 0
    
    try:
        if path.is_file():
            size = path.stat().st_size
            path.unlink()
        else:
            size = get_dir_size(path)
            shutil.rmtree(path)
        
        if verbose:
            print(f"   removed: {path} ({format_size(size)})")
        return size
    except Exception as e:
        if verbose:
            print(f"   WARN: cannot remove {path}: {e}")
        return 0


def resolve_lib_dir(python_dir: Path) -> Path:
    """Resolve stdlib directory for Unix/Windows layouts."""
    candidates = [
        python_dir / "lib" / "python3.11",
        python_dir / "Lib",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def optimize_python(python_dir: Path, aggressive: bool = False, verbose: bool = True) -> None:
    """
    优化 PBS Python 体积
    
    Args:
        python_dir: Python 安装目录
        aggressive: 是否启用激进优化（删除 pip/setuptools）
        verbose: 是否显示详细信息
    """
    if not python_dir.exists():
        raise FileNotFoundError(f"Python directory not found: {python_dir}")
    
    initial_size = get_dir_size(python_dir)
    print(f"Size before optimization: {format_size(initial_size)}")
    print()
    
    total_freed = 0
    
    # 1. 删除测试文件
    print("Cleaning test files...")
    for pattern in ["test", "tests", "testing"]:
        for test_dir in python_dir.rglob(pattern):
            if test_dir.is_dir():
                total_freed += remove_safely(test_dir, verbose)
    
    # 2. 删除 __pycache__ 目录
    print("Cleaning __pycache__...")
    for cache_dir in python_dir.rglob("__pycache__"):
        if cache_dir.is_dir():
            total_freed += remove_safely(cache_dir, verbose)
    
    # 3. 删除 .pyc 文件（可选，运行时会重新生成）
    print("Cleaning .pyc files...")
    for pyc_file in python_dir.rglob("*.pyc"):
        total_freed += remove_safely(pyc_file, verbose)
    
    # 4. 删除不需要的标准库模块
    print("Cleaning unnecessary stdlib modules...")
    lib_dir = resolve_lib_dir(python_dir)
    for module in UNNECESSARY_MODULES:
        module_path = lib_dir / module
        total_freed += remove_safely(module_path, verbose)
        # 也检查 .py 文件
        py_file = lib_dir / f"{module}.py"
        total_freed += remove_safely(py_file, verbose)
    
    # 5. 删除文档和示例
    print("Cleaning docs and examples...")
    site_packages_dir = lib_dir / "site-packages"
    for pattern in ["*.md", "*.rst", "*.txt"]:
        for doc_file in python_dir.rglob(pattern):
            # 保护 Python 包元数据，避免破坏 importlib.metadata entry_points
            # 例如 opentelemetry 依赖 .dist-info/entry_points.txt 来加载 runtime context
            if site_packages_dir in doc_file.parents:
                parent_name = doc_file.parent.name
                if (
                    parent_name.endswith(".dist-info")
                    or parent_name.endswith(".egg-info")
                    or parent_name.endswith(".data")
                ):
                    if doc_file.name.lower() in METADATA_TXT_BASENAMES:
                        continue
                    if parent_name.endswith(".dist-info") or parent_name.endswith(".egg-info"):
                        continue
            # 保留 LICENSE 文件
            if "license" in doc_file.name.lower():
                continue
            total_freed += remove_safely(doc_file, verbose)
    
    for pattern in ["examples", "docs", "doc", "samples"]:
        for doc_dir in python_dir.rglob(pattern):
            if doc_dir.is_dir():
                total_freed += remove_safely(doc_dir, verbose)
    
    # 6. 激进优化：删除 pip 和 setuptools
    if aggressive:
        print("Aggressive mode: removing pip and setuptools...")
        site_packages = lib_dir / "site-packages"
        if site_packages.exists():
            for pkg in ["pip", "setuptools", "pkg_resources"]:
                for item in site_packages.glob(f"{pkg}*"):
                    total_freed += remove_safely(item, verbose)
    
    # 7. 删除 include 目录（C 头文件，运行时不需要）
    print("Cleaning include directory...")
    include_dir = python_dir / "include"
    total_freed += remove_safely(include_dir, verbose)
    
    # 8. 删除共享库调试符号（仅限 release 构建）
    print("Cleaning shared libraries...")
    for so_file in python_dir.rglob("*.so"):
        # 不删除核心库，只删除测试相关的
        if "test" in so_file.name.lower():
            total_freed += remove_safely(so_file, verbose)
    
    final_size = get_dir_size(python_dir)
    
    print()
    print("=" * 50)
    print(f"Size before: {format_size(initial_size)}")
    print(f"Size after:  {format_size(final_size)}")
    if initial_size > 0:
        ratio = total_freed * 100 / initial_size
    else:
        ratio = 0.0
    print(f"Freed space: {format_size(total_freed)} ({ratio:.1f}%)")
    print("=" * 50)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <python_dir> [--aggressive] [--verbose]")
        print("\nOptions:")
        print("  --aggressive  enable aggressive optimization (remove pip/setuptools)")
        print("  --verbose     show detailed removal logs")
        sys.exit(1)
    
    python_dir = Path(sys.argv[1])
    aggressive = "--aggressive" in sys.argv
    verbose = "--verbose" in sys.argv
    
    try:
        optimize_python(python_dir, aggressive, verbose)
    except Exception as e:
        print(f"\nERROR: optimization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
