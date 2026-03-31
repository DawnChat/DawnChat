#!/usr/bin/env python3
"""
scripts/compile_cython.py
使用 Cython 编译核心 Python 模块为 .so/.pyd 文件

用于源代码保护：将 .py 文件编译为 C 扩展模块，
比 .pyc 提供更强的代码保护。

使用方法:
    python compile_cython.py <source_dir> <output_dir> [--modules module1,module2]

示例:
    # 编译 workflows 目录
    python compile_cython.py ./app/workflows ./dist/app/workflows
    
    # 只编译指定模块
    python compile_cython.py ./app ./dist/app --modules workflows,agents
"""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import List

# 默认需要编译的核心目录
DEFAULT_CORE_MODULES = [
    "workflows",  # 工作流引擎
]

# 需要跳过的文件和目录
SKIP_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "__init__.py",  # __init__.py 保留为源码（通常只有 import 语句）
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "schema.py",    # Pydantic Schema 定义，编译后会导致注解丢失
    "routes.py",    # FastAPI 路由定义，Cython 对 Query/Body 等默认值类型检查有问题
]


def should_skip(path: Path) -> bool:
    """检查是否应该跳过此文件"""
    # 跳过 models 目录 (Pydantic 模型定义)
    if "models" in path.parts:
        return True
        
    # 跳过 api 目录 (FastAPI 路由定义)
    if "api" in path.parts:
        return True
        
    name = path.name
    
    for pattern in SKIP_PATTERNS:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif pattern.endswith("*"):
            if name.startswith(pattern[:-1]):
                return True
        else:
            if name == pattern:
                return True
    
    return False


def get_python_files(source_dir: Path, modules: List[str] = None) -> List[Path]:
    """
    获取需要编译的 Python 文件列表
    
    Args:
        source_dir: 源代码目录
        modules: 指定的模块列表（相对路径）
    
    Returns:
        Python 文件路径列表
    """
    files = []
    
    if modules:
        # 只处理指定的模块
        for module in modules:
            module_path = source_dir / module
            if module_path.exists():
                for py_file in module_path.rglob("*.py"):
                    if not should_skip(py_file):
                        files.append(py_file)
    else:
        # 处理整个源码目录
        for py_file in source_dir.rglob("*.py"):
            if not should_skip(py_file):
                files.append(py_file)
    
    return files


def create_setup_py(source_files: List[Path], output_dir: Path) -> Path:
    """
    创建临时的 setup.py 用于 Cython 编译
    """
    # 生成模块定义
    modules_code = []
    for f in source_files:
        # 计算相对路径作为模块名
        rel_path = f.relative_to(f.parent.parent.parent)  # 相对于 app 的父目录
        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
        modules_code.append(f'    Extension("{module_name}", ["{f}"])')
    
    modules_str = ",\n".join(modules_code)
    
    setup_content = f'''
"""
临时 setup.py - 用于 Cython 编译
自动生成，请勿手动修改
"""
from setuptools import setup
from setuptools.extension import Extension
from Cython.Build import cythonize

ext_modules = [
{modules_str}
]

setup(
    name="dawnchat-compiled",
    ext_modules=cythonize(
        ext_modules,
        compiler_directives={{
            "language_level": "3",  # Python 3
            "boundscheck": False,   # 关闭边界检查（提升性能）
            "wraparound": False,    # 关闭负索引（提升性能）
        }},
        nthreads=4  # 并行编译
    ),
)
'''
    
    setup_path = output_dir / "setup_cython.py"
    setup_path.write_text(setup_content)
    return setup_path


def compile_single_file(
    source_file: Path,
    output_dir: Path,
    python_executable: str = "python3"
) -> bool:
    """
    编译单个 Python 文件为 .so/.pyd
    
    Args:
        source_file: 源文件路径
        output_dir: 输出目录
        python_executable: Python 可执行文件
    
    Returns:
        是否成功
    """
    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # 复制源文件
        tmp_source = tmp_path / source_file.name
        shutil.copy(source_file, tmp_source)
        
        # 创建 setup.py
        module_name = source_file.stem
        setup_content = f'''
from setuptools import setup
from setuptools.extension import Extension
from Cython.Build import cythonize

setup(
    ext_modules=cythonize(
        Extension("{module_name}", ["{tmp_source}"]),
        compiler_directives={{"language_level": "3"}}
    ),
)
'''
        setup_path = tmp_path / "setup.py"
        setup_path.write_text(setup_content)
        
        # 编译
        result = subprocess.run(
            [python_executable, str(setup_path), "build_ext", "--inplace"],
            cwd=tmp_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"   ❌ 编译失败: {source_file}")
            print(f"      {result.stderr}")
            return False
        
        # 查找生成的 .so/.pyd 文件
        ext = ".pyd" if platform.system() == "Windows" else ".so"
        compiled_files = list(tmp_path.glob(f"*{ext}"))
        
        if not compiled_files:
            print(f"   ❌ 未找到编译产物: {source_file}")
            return False
        
        # 复制到输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        for cf in compiled_files:
            dest = output_dir / cf.name
            shutil.copy(cf, dest)
            print(f"   ✅ {source_file.name} -> {cf.name}")
        
        return True


def compile_with_cython(
    source_dir: Path,
    output_dir: Path,
    modules: List[str] = None,
    python_executable: str = "python3",
    keep_source: bool = False
) -> bool:
    """
    使用 Cython 编译 Python 模块
    
    Args:
        source_dir: 源代码目录
        output_dir: 输出目录
        modules: 要编译的模块列表
        python_executable: Python 可执行文件路径
        keep_source: 是否保留源代码
    
    Returns:
        是否成功
    """
    print("🔧 Cython 编译开始")
    print(f"   源目录: {source_dir}")
    print(f"   输出目录: {output_dir}")
    print(f"   指定模块: {modules or '全部'}")
    print()
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果源目录和输出目录不同，则复制
    if source_dir.resolve() != output_dir.resolve():
        # 首先复制整个源码目录
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(source_dir, output_dir)
    else:
        print("ℹ️  源目录与输出目录相同，进行原地编译")
    
    # 获取需要编译的文件
    if modules:
        files_to_compile = []
        for module in modules:
            module_path = output_dir / module
            if module_path.exists():
                for py_file in module_path.rglob("*.py"):
                    if not should_skip(py_file):
                        files_to_compile.append(py_file)
    else:
        files_to_compile = get_python_files(output_dir, DEFAULT_CORE_MODULES)
    
    if not files_to_compile:
        print("⚠️ 没有找到需要编译的文件")
        return True
    
    print(f"📋 需要编译 {len(files_to_compile)} 个文件:")
    for f in files_to_compile:
        print(f"   - {f.relative_to(output_dir)}")
    print()
    
    # 检查 Cython 是否可用
    result = subprocess.run(
        [python_executable, "-c", "import Cython; print(Cython.__version__)"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("❌ Cython 未安装，请先运行: pip install cython")
        return False
    print(f"   Cython 版本: {result.stdout.strip()}")
    print()
    
    # 编译每个文件
    success_count = 0
    fail_count = 0
    
    print("🔨 开始编译...")
    for source_file in files_to_compile:
        # 计算输出目录
        rel_path = source_file.relative_to(output_dir)
        file_output_dir = output_dir / rel_path.parent
        
        if compile_single_file(source_file, file_output_dir, python_executable):
            success_count += 1
            
            # 删除源文件（除非 keep_source=True）
            if not keep_source:
                source_file.unlink()
        else:
            fail_count += 1
    
    print()
    print("=" * 50)
    print(f"📊 编译完成: 成功 {success_count}, 失败 {fail_count}")
    print("=" * 50)
    
    return fail_count == 0


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="使用 Cython 编译 Python 模块",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 编译整个 app 目录中的 workflows 模块
  %(prog)s ./app ./dist/app --modules workflows
  
  # 编译并保留源文件（用于调试）
  %(prog)s ./app ./dist/app --modules workflows --keep-source
  
  # 使用指定的 Python
  %(prog)s ./app ./dist/app --python /path/to/python
"""
    )
    
    parser.add_argument("source_dir", help="源代码目录")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--modules", help="要编译的模块，逗号分隔")
    parser.add_argument("--python", default="python3", help="Python 可执行文件")
    parser.add_argument("--keep-source", action="store_true", help="保留源文件")
    
    args = parser.parse_args()
    
    source_dir = Path(args.source_dir)
    output_dir = Path(args.output_dir)
    modules = args.modules.split(",") if args.modules else None
    
    if not source_dir.exists():
        print(f"❌ 源目录不存在: {source_dir}")
        sys.exit(1)
    
    try:
        success = compile_with_cython(
            source_dir,
            output_dir,
            modules,
            args.python,
            args.keep_source
        )
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 编译失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()





