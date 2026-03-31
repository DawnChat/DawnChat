"""
AI 代码执行环境管理器

实现与 App 运行时的隔离，同时复用已安装的依赖。

设计原则:
1. AI 执行环境与 App 运行时环境完全隔离
2. AI 环境可以复用 App 已安装的包（通过继承 site-packages）
3. AI 执行的代码无法修改 App 的运行时环境
4. 支持为 AI 任务动态安装新的依赖

环境架构:
┌─────────────────────────────────────────────────────────────────┐
│  App 运行时环境 (只读)                                         │
│  python/lib/python3.11/site-packages/                          │
│  ├── fastapi/                                                  │
│  ├── litellm/                                                  │
│  └── [所有预装依赖]                                             │
└─────────────────────────────────────────────────────────────────┘
                           ▲
                           │ 继承 (PYTHONPATH)
                           │
┌─────────────────────────────────────────────────────────────────┐
│  AI 执行 venv (可写)                                           │
│  ~/Library/Application Support/DawnChat/ai_venv/                 │
│  ├── pyvenv.cfg                                                │
│  ├── lib/python3.11/site-packages/                             │
│  │   └── [AI 任务安装的额外依赖]                                │
│  └── bin/                                                      │
│      └── python3 -> ../../python/bin/python3.11                │
└─────────────────────────────────────────────────────────────────┘
"""

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional
import venv

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("ai_sandbox")


class AIExecutionEnv:
    """
    AI 代码执行环境

    提供与 App 运行时隔离的 Python 执行环境。

    使用示例:
        env = get_ai_env()
        await env.initialize()

        # 执行代码
        result = await env.execute_code("print('Hello from AI sandbox')")
        print(result["stdout"])

        # 安装额外的包
        await env.install_package("numpy")
    """

    # 用户数据目录下的 AI venv
    AI_VENV_DIR = Config.DATA_DIR / "ai_venv"

    def __init__(self):
        """初始化环境管理器"""
        self._initialized = False
        self._python_path: Optional[Path] = None
        self._pip_path: Optional[Path] = None

    @property
    def python_path(self) -> Optional[Path]:
        """获取 venv 的 Python 路径"""
        return self._python_path

    @property
    def pip_path(self) -> Optional[Path]:
        """获取 venv 的 pip 路径"""
        return self._pip_path

    @property
    def is_initialized(self) -> bool:
        """检查环境是否已初始化"""
        return self._initialized

    async def initialize(self) -> bool:
        """
        初始化 AI 执行环境

        - 如果 venv 不存在，创建新的
        - 如果存在，验证其有效性

        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True

        try:
            if not self.AI_VENV_DIR.exists():
                await self._create_venv()
            else:
                # 验证 venv 有效性
                if not self._validate_venv():
                    logger.warning("AI venv 无效，重新创建...")
                    await self._recreate_venv()

            self._python_path = self._get_python_path()
            self._pip_path = self._get_pip_path()
            self._initialized = True

            logger.info(f"✅ AI 执行环境就绪: {self.AI_VENV_DIR}")
            return True

        except Exception as e:
            logger.error(f"❌ AI 执行环境初始化失败: {e}", exc_info=True)
            return False

    def _get_app_python(self) -> Path:
        """获取 App 嵌入的 Python 路径"""
        if getattr(sys, "frozen", False):
            # PBS 打包环境
            # Python 位于 sidecar 目录的 python 子目录
            base = Path(sys.executable).parent
            if sys.platform == "win32":
                return base / "python" / "python.exe"
            else:
                return base / "python" / "bin" / "python3.11"
        else:
            # 开发环境，使用系统 Python
            return Path(sys.executable)

    def _get_app_site_packages(self) -> Path:
        """获取 App 的 site-packages 路径"""
        if getattr(sys, "frozen", False):
            # PBS 打包环境
            base = Path(sys.executable).parent
            if sys.platform == "win32":
                return base / "python" / "Lib" / "site-packages"
            else:
                return base / "python" / "lib" / "python3.11" / "site-packages"
        else:
            # 开发环境
            import site

            sites = site.getsitepackages()
            if sites:
                return Path(sites[0])
            # 回退到用户 site-packages
            return Path(site.getusersitepackages())

    async def _create_venv(self) -> None:
        """
        创建 AI 执行 venv

        关键：使用 --system-site-packages 继承 App 的依赖
        """
        logger.info(f"🔧 创建 AI 执行环境: {self.AI_VENV_DIR}")

        # 确保父目录存在
        self.AI_VENV_DIR.parent.mkdir(parents=True, exist_ok=True)

        # 使用 venv 模块创建
        # system_site_packages=True: 继承系统（App）的 site-packages
        builder = venv.EnvBuilder(
            system_site_packages=True,  # 关键！继承 App 依赖
            clear=True,
            with_pip=True,
        )

        # 在线程池中执行（venv.create 是同步的）
        await asyncio.to_thread(builder.create, str(self.AI_VENV_DIR))

        # 配置 pyvenv.cfg 确保继承系统包
        cfg_path = self.AI_VENV_DIR / "pyvenv.cfg"
        if cfg_path.exists():
            cfg_content = cfg_path.read_text()
            if "include-system-site-packages" not in cfg_content:
                with open(cfg_path, "a") as f:
                    f.write("\ninclude-system-site-packages = true\n")

        logger.info("✅ AI 执行环境创建成功")

    async def _recreate_venv(self) -> None:
        """重新创建 venv"""
        if self.AI_VENV_DIR.exists():
            shutil.rmtree(self.AI_VENV_DIR)
        await self._create_venv()

    def _validate_venv(self) -> bool:
        """验证 venv 是否有效"""
        python_path = self._get_python_path()
        return python_path.exists() and python_path.is_file()

    def _get_python_path(self) -> Path:
        """获取 venv 的 Python 路径"""
        if sys.platform == "win32":
            return self.AI_VENV_DIR / "Scripts" / "python.exe"
        else:
            return self.AI_VENV_DIR / "bin" / "python3"

    def _get_pip_path(self) -> Path:
        """获取 venv 的 pip 路径"""
        if sys.platform == "win32":
            return self.AI_VENV_DIR / "Scripts" / "pip.exe"
        else:
            return self.AI_VENV_DIR / "bin" / "pip3"

    async def install_package(self, package: str, timeout: int = 300) -> bool:
        """
        在 AI 环境中安装额外的包

        注意：安装到 AI venv，不影响 App 运行时

        Args:
            package: 包名（可以包含版本号，如 "numpy==1.24.0"）
            timeout: 超时时间（秒）

        Returns:
            是否安装成功
        """
        if not self._initialized:
            await self.initialize()

        try:
            logger.info(f"📦 AI 环境安装包: {package}")

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    [str(self._pip_path), "install", "--no-cache-dir", package],
                    capture_output=True,
                    text=True,
                ),
                timeout=timeout,
            )

            if result.returncode == 0:
                logger.info(f"✅ 包安装成功: {package}")
                return True
            else:
                logger.error(f"❌ 包安装失败: {result.stderr}")
                return False

        except asyncio.TimeoutError:
            logger.error(f"❌ 包安装超时: {package} ({timeout}s)")
            return False
        except Exception as e:
            logger.error(f"❌ 包安装异常: {e}")
            return False

    async def execute_code(
        self, code: str, timeout: int = 30, env_vars: Optional[Dict[str, str]] = None, cwd: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        在 AI 环境中执行代码

        Args:
            code: 要执行的 Python 代码
            timeout: 超时时间（秒）
            env_vars: 额外的环境变量
            cwd: 工作目录

        Returns:
            {
                "success": bool,
                "stdout": str,
                "stderr": str,
                "exit_code": int
            }
        """
        if not self._initialized:
            await self.initialize()

        try:
            # 准备环境变量
            env = os.environ.copy()

            # 设置 PYTHONPATH 包含 App 的 site-packages
            app_site_packages = self._get_app_site_packages()
            existing_path = env.get("PYTHONPATH", "")
            if existing_path:
                env["PYTHONPATH"] = f"{app_site_packages}:{existing_path}"
            else:
                env["PYTHONPATH"] = str(app_site_packages)

            # 合并用户提供的环境变量
            if env_vars:
                env.update(env_vars)

            # 默认工作目录
            work_dir = cwd or Config.DATA_DIR

            # 执行代码
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    [str(self._python_path), "-c", code],
                    capture_output=True,
                    text=True,
                    env=env,
                    cwd=str(work_dir),
                ),
                timeout=timeout,
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }

        except asyncio.TimeoutError:
            return {"success": False, "stdout": "", "stderr": f"执行超时（{timeout}秒）", "exit_code": -1}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}

    async def execute_script(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        timeout: int = 60,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        在 AI 环境中执行脚本文件

        Args:
            script_path: 脚本文件路径
            args: 命令行参数
            timeout: 超时时间（秒）
            env_vars: 额外的环境变量

        Returns:
            与 execute_code 相同的结果格式
        """
        if not self._initialized:
            await self.initialize()

        cmd = [str(self._python_path), str(script_path)]
        if args:
            cmd.extend(args)

        try:
            env = os.environ.copy()
            app_site_packages = self._get_app_site_packages()
            env["PYTHONPATH"] = str(app_site_packages)

            if env_vars:
                env.update(env_vars)

            result = await asyncio.wait_for(
                asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                ),
                timeout=timeout,
            )

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
            }

        except asyncio.TimeoutError:
            return {"success": False, "stdout": "", "stderr": f"执行超时（{timeout}秒）", "exit_code": -1}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}

    def get_available_packages(self) -> List[str]:
        """
        获取 AI 环境可用的包列表

        Returns:
            包名列表
        """
        if not self._initialized:
            return []

        try:
            result = subprocess.run(
                [str(self._pip_path), "list", "--format=freeze"], capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return [line.split("==")[0] for line in result.stdout.strip().split("\n") if line and "==" in line]
            return []
        except Exception:
            return []

    async def cleanup(self) -> None:
        """
        清理 AI 执行环境

        完全删除 venv，下次使用时会重新创建
        """
        if self.AI_VENV_DIR.exists():
            logger.info(f"🧹 清理 AI 执行环境: {self.AI_VENV_DIR}")
            shutil.rmtree(self.AI_VENV_DIR)
            self._initialized = False
            self._python_path = None
            self._pip_path = None
            logger.info("✅ AI 执行环境已清理")


# ============ 单例 ============

_ai_env: Optional[AIExecutionEnv] = None


def get_ai_env() -> AIExecutionEnv:
    """
    获取 AI 执行环境单例

    使用示例:
        env = get_ai_env()
        await env.initialize()
        result = await env.execute_code("print('Hello')")

    Returns:
        AIExecutionEnv 实例
    """
    global _ai_env
    if _ai_env is None:
        _ai_env = AIExecutionEnv()
    return _ai_env
