"""
DawnChat - Llama.cpp 二进制管理器
负责管理 llama-server 二进制文件的部署和版本管理

目录结构说明：
- 预置二进制目录：llamacpp/llama-b7204-bin-{platform}/bin/
- 部署目标目录：Config.BIN_DIR (用户数据目录)

打包环境说明：
- 开发环境：llamacpp/ 目录包含所有平台的子目录
- 打包环境：llamacpp/ 目录只包含当前平台的一个子目录（由 build.sh 复制）
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
from typing import Dict, Optional

from app.config import Config
from app.utils.logger import setup_logger

logger = setup_logger("dawnchat.llama_binary", log_file=Config.LOGS_DIR / "llama.log")


# 预置二进制目录映射表
BINARY_DIRS = {
    # (OS, 架构, 变体) -> 目录名
    ("Darwin", "arm64", "cpu"): "llama-b7204-bin-macos-arm64",
    ("Darwin", "x86_64", "cpu"): "llama-b7204-bin-macos-x64",
    ("Linux", "x86_64", "cpu"): "llama-b7204-bin-ubuntu-x64",
    ("Windows", "AMD64", "cpu"): "llama-b7204-bin-win-cpu-x64",
    ("Windows", "ARM64", "cpu"): "llama-b7204-bin-win-cpu-arm64",
}

# 平台关键字映射（用于自动检测目录）
PLATFORM_KEYWORDS = {
    ("Darwin", "arm64"): ["macos-arm64", "macos-aarch64", "darwin-arm64"],
    ("Darwin", "x86_64"): ["macos-x64", "macos-x86_64", "darwin-x64"],
    ("Linux", "x86_64"): ["ubuntu-x64", "linux-x64", "linux-x86_64"],
    ("Windows", "AMD64"): ["win-cpu-x64", "win-x64", "windows-x64"],
    ("Windows", "ARM64"): ["win-cpu-arm64", "win-arm64", "windows-arm64"],
}

# GPU 版本需要从 GitHub 下载
GPU_BINARY_URLS = {
    "cuda-12": "https://github.com/ggml-org/llama.cpp/releases/download/b7204/llama-b7204-bin-win-cuda-12.4.0-x64.zip",
    "vulkan": "https://github.com/ggml-org/llama.cpp/releases/download/b7204/llama-b7204-bin-win-vulkan-x64.zip",
}

# 当前二进制版本
BINARY_VERSION = "b7204"

# 是否为打包环境
IS_FROZEN = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


class LlamaBinaryManager:
    """
    Llama.cpp 二进制管理器
    
    职责：
    1. 环境检测：识别 OS 和架构
    2. 解压部署：从预置 zip 解压到用户目录
    3. 版本管理：检查本地版本，支持升级
    4. GPU 支持：提供 API 让用户触发 GPU 版本下载
    """
    
    _instance: Optional['LlamaBinaryManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._platform_info = self._detect_platform()
        self._version_file = Config.BIN_DIR / "version.json"
        logger.info(f"二进制管理器初始化: {self._platform_info}")
    
    def _detect_platform(self) -> Dict[str, str]:
        """检测当前平台信息"""
        system = platform.system()
        machine = platform.machine()
        
        # 标准化架构名称
        arch = machine
        if machine in ("x86_64", "AMD64"):
            arch = "x86_64" if system != "Windows" else "AMD64"
        elif machine in ("arm64", "aarch64", "ARM64"):
            arch = "arm64" if system != "Windows" else "ARM64"
        
        return {
            "system": system,
            "machine": arch,
            "python_version": platform.python_version(),
        }
    
    def get_platform_dir_name(self) -> Optional[str]:
        """获取当前平台对应的预置二进制目录名"""
        key = (self._platform_info["system"], self._platform_info["machine"], "cpu")
        dir_name = BINARY_DIRS.get(key)
        
        if not dir_name:
            logger.warning(f"未找到当前平台的预置二进制映射: {key}")
            return None
        
        return dir_name
    
    def _find_matching_dir(self) -> Optional[Path]:
        """
        在 llamacpp 目录中查找匹配当前平台的二进制目录
        
        打包环境下，目录中只有一个平台目录，直接使用即可
        开发环境下，根据平台关键字匹配
        """
        resources_dir = Config.LLAMACPP_RESOURCES_DIR
        
        if not resources_dir.exists():
            logger.warning(f"llamacpp 资源目录不存在: {resources_dir}")
            return None
        
        # 获取目录中所有包含 bin 子目录的平台目录
        platform_dirs = [
            d for d in resources_dir.iterdir()
            if d.is_dir() and (d / "bin").exists() and not d.name.startswith(".")
        ]
        
        if not platform_dirs:
            logger.warning(f"llamacpp 目录中没有有效的平台目录: {resources_dir}")
            return None
        
        # 打包环境：如果只有一个平台目录，直接使用
        if IS_FROZEN and len(platform_dirs) == 1:
            logger.info(f"打包环境检测到单个平台目录: {platform_dirs[0].name}")
            return platform_dirs[0]
        
        # 开发环境或多个目录：根据平台关键字匹配
        platform_key = (self._platform_info["system"], self._platform_info["machine"])
        keywords = PLATFORM_KEYWORDS.get(platform_key, [])
        
        if not keywords:
            logger.warning(f"未找到平台关键字映射: {platform_key}")
            # 尝试使用 BINARY_DIRS 的精确匹配
            dir_name = self.get_platform_dir_name()
            if dir_name:
                dir_path = resources_dir / dir_name
                if dir_path.exists() and (dir_path / "bin").exists():
                    return dir_path
            return None
        
        # 查找包含平台关键字的目录
        for platform_dir in platform_dirs:
            dirname_lower = platform_dir.name.lower()
            for keyword in keywords:
                if keyword.lower() in dirname_lower:
                    logger.info(f"匹配到平台目录: {platform_dir.name} (关键字: {keyword})")
                    return platform_dir
        
        logger.warning(f"未找到匹配当前平台的目录，平台: {platform_key}, 关键字: {keywords}")
        return None
    
    def get_source_bin_dir(self) -> Optional[Path]:
        """获取预置二进制的 bin 目录路径"""
        # 首先尝试精确匹配
        dir_name = self.get_platform_dir_name()
        if dir_name:
            dir_path = Config.LLAMACPP_RESOURCES_DIR / dir_name
            bin_path = dir_path / "bin"
            if bin_path.exists():
                return bin_path
        
        # 精确匹配失败，尝试自动检测
        logger.info("精确匹配失败，尝试自动检测平台目录...")
        platform_dir = self._find_matching_dir()
        if platform_dir:
            return platform_dir / "bin"
        return None
    
    def _get_local_version(self) -> Optional[Dict]:
        """获取本地已部署的二进制版本信息"""
        if not self._version_file.exists():
            return None
        
        try:
            with open(self._version_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取版本文件失败: {e}")
            return None
    
    def _save_version_info(self, variant: str = "cpu"):
        """保存版本信息"""
        version_info = {
            "version": BINARY_VERSION,
            "variant": variant,
            "platform": self._platform_info,
            "deployed_at": datetime.now().isoformat(),
        }
        
        try:
            with open(self._version_file, 'w') as f:
                json.dump(version_info, f, indent=2)
            logger.info(f"版本信息已保存: {version_info}")
        except Exception as e:
            logger.error(f"保存版本信息失败: {e}")
    
    def needs_deploy(self) -> bool:
        """检查是否需要部署二进制"""
        executable = Config.get_llama_server_executable()
        
        # 可执行文件不存在
        if not executable.exists():
            return True
        
        # 版本检查
        local_version = self._get_local_version()
        if not local_version:
            return True
        
        if local_version.get("version") != BINARY_VERSION:
            logger.info(f"版本不匹配: 本地={local_version.get('version')}, 最新={BINARY_VERSION}")
            return True
        
        return False
    
    async def ensure_binary(self) -> Optional[Path]:
        """
        确保二进制可用，返回可执行文件路径
        
        如果已部署且版本匹配，直接返回路径
        否则从预置目录复制部署
        """
        executable = Config.get_llama_server_executable()
        
        # 打印环境信息便于调试
        logger.info(f"运行环境: {'打包' if IS_FROZEN else '开发'}")
        logger.info(f"llamacpp 资源目录: {Config.LLAMACPP_RESOURCES_DIR}")
        logger.info(f"二进制部署目录: {Config.BIN_DIR}")
        logger.info(f"目标可执行文件: {executable}")
        
        if not self.needs_deploy():
            logger.info(f"二进制已就绪: {executable}")
            return executable
        
        logger.info("开始部署 llama-server 二进制...")
        
        # 获取预置 bin 目录路径
        source_bin_dir = self.get_source_bin_dir()
        if not source_bin_dir:
            logger.error(f"未找到预置二进制目录，检查目录: {Config.LLAMACPP_RESOURCES_DIR}")
            # 列出目录内容帮助调试
            if Config.LLAMACPP_RESOURCES_DIR.exists():
                items = list(Config.LLAMACPP_RESOURCES_DIR.iterdir())
                logger.error(f"目录内容: {[f.name for f in items]}")
            else:
                logger.error("llamacpp 资源目录不存在")
            return None
        
        logger.info(f"使用预置目录: {source_bin_dir}")
        
        # 复制部署
        success = await self._deploy_binary(source_bin_dir)
        if not success:
            return None
        
        return executable if executable.exists() else None
    
    async def _deploy_binary(self, source_bin_dir: Path) -> bool:
        """从预置 bin 目录复制二进制文件到部署目录"""
        try:
            # 清理旧文件
            if Config.BIN_DIR.exists():
                logger.info(f"清理旧目录: {Config.BIN_DIR}")
                shutil.rmtree(Config.BIN_DIR)
            
            Config.BIN_DIR.mkdir(parents=True, exist_ok=True)
            
            # 在线程中复制（避免阻塞）
            def copy_files():
                file_count = 0
                for item in source_bin_dir.iterdir():
                    target_path = Config.BIN_DIR / item.name
                    
                    if item.is_file():
                        shutil.copy2(item, target_path)
                        file_count += 1
                        
                        # 如果是可执行文件，添加执行权限
                        if item.name in ("llama-server", "llama-cli", "llama-quantize"):
                            os.chmod(target_path, target_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                            logger.debug(f"已添加执行权限: {target_path}")
                    elif item.is_dir():
                        shutil.copytree(item, target_path)
                        file_count += 1
                
                logger.info(f"已复制 {file_count} 个文件/目录")
            
            await asyncio.to_thread(copy_files)
            
            # 验证可执行文件
            executable = Config.get_llama_server_executable()
            if not executable.exists():
                logger.error(f"复制后未找到可执行文件: {executable}")
                # 列出复制后的文件
                for f in Config.BIN_DIR.rglob("*"):
                    logger.debug(f"  - {f}")
                return False
            
            # 确保有执行权限
            if platform.system() != "Windows":
                os.chmod(executable, executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            
            # 保存版本信息
            self._save_version_info("cpu")
            
            logger.info(f"✅ 二进制部署成功: {executable}")
            return True
            
        except Exception as e:
            logger.error(f"部署二进制失败: {e}", exc_info=True)
            return False
    
    async def download_gpu_binary(self, variant: str) -> bool:
        """
        下载 GPU 版本二进制（仅 Windows）
        
        Args:
            variant: 'cuda-12' 或 'vulkan'
        
        Returns:
            是否下载成功
        """
        if self._platform_info["system"] != "Windows":
            logger.warning("GPU 版本仅支持 Windows")
            return False
        
        if variant not in GPU_BINARY_URLS:
            logger.error(f"未知的 GPU 变体: {variant}")
            return False
        
        url = GPU_BINARY_URLS[variant]
        logger.info(f"开始下载 GPU 版本: {variant} from {url}")
        
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                # 保存到临时文件
                temp_zip = Config.BIN_DIR.parent / f"llama-{variant}.zip"
                with open(temp_zip, 'wb') as f:
                    f.write(response.content)
                
                # 部署
                success = await self._deploy_binary(temp_zip)
                
                # 清理临时文件
                temp_zip.unlink(missing_ok=True)
                
                if success:
                    self._save_version_info(variant)
                
                return success
                
        except Exception as e:
            logger.error(f"下载 GPU 版本失败: {e}", exc_info=True)
            return False
    
    def get_binary_info(self) -> Dict:
        """获取当前二进制信息"""
        executable = Config.get_llama_server_executable()
        local_version = self._get_local_version()
        source_bin_dir = self.get_source_bin_dir()
        
        return {
            "platform": self._platform_info,
            "is_frozen": IS_FROZEN,
            "resources_dir": str(Config.LLAMACPP_RESOURCES_DIR),
            "resources_dir_exists": Config.LLAMACPP_RESOURCES_DIR.exists(),
            "source_bin_dir": str(source_bin_dir) if source_bin_dir else None,
            "source_bin_dir_exists": source_bin_dir.exists() if source_bin_dir else False,
            "bin_dir": str(Config.BIN_DIR),
            "executable_path": str(executable),
            "executable_exists": executable.exists(),
            "version": local_version.get("version") if local_version else None,
            "variant": local_version.get("variant") if local_version else None,
            "deployed_at": local_version.get("deployed_at") if local_version else None,
            "latest_version": BINARY_VERSION,
            "needs_update": self.needs_deploy(),
        }


# 全局单例
_binary_manager: Optional[LlamaBinaryManager] = None


def get_binary_manager() -> LlamaBinaryManager:
    """获取二进制管理器单例"""
    global _binary_manager
    if _binary_manager is None:
        _binary_manager = LlamaBinaryManager()
    return _binary_manager

