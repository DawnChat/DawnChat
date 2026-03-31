"""
ADB 设备管理服务

负责 ADB 进程管理、设备发现、命令执行和状态维护。
遵循 DawnChat Phase 1 架构设计。

核心职责：
1. ADB 进程管理：确保 adb server 运行，自动启动/重启
2. 设备管理：发现设备、维护设备列表、设备锁
3. 命令执行：统一接口、超时控制、自动重试
4. 坐标系统：归一化坐标(0-1000) ↔ 绝对像素坐标转换
5. 日志记录：记录所有命令和错误
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
import platform
import shutil
import time
from typing import Dict, List, Optional, Tuple

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("adb_manager")


# =============================================================================
# 数据模型
# =============================================================================

class DeviceStatus(str, Enum):
    """设备状态"""
    ONLINE = "device"           # 在线
    OFFLINE = "offline"         # 离线
    UNAUTHORIZED = "unauthorized"  # 未授权
    UNKNOWN = "unknown"         # 未知


@dataclass
class DeviceInfo:
    """设备信息"""
    serial: str                 # 设备序列号
    status: DeviceStatus        # 设备状态
    model: Optional[str] = None  # 设备型号
    android_version: Optional[str] = None  # Android 版本
    screen_width: Optional[int] = None  # 屏幕宽度（像素）
    screen_height: Optional[int] = None  # 屏幕高度（像素）
    screen_density: Optional[int] = None  # 屏幕密度 (dpi)
    battery_level: Optional[int] = None  # 电池电量
    current_app: Optional[str] = None  # 当前应用包名
    locked: bool = False        # 是否被任务锁定
    last_seen: Optional[datetime] = None  # 最后一次发现时间
    
    def __post_init__(self):
        if self.last_seen is None:
            self.last_seen = datetime.now()


@dataclass
class CommandResult:
    """命令执行结果"""
    success: bool               # 是否成功
    stdout: str                 # 标准输出
    stderr: str                 # 标准错误
    return_code: int            # 返回码
    duration_ms: float          # 执行时长（毫秒）
    command: str                # 执行的命令


# =============================================================================
# ADB Manager
# =============================================================================

class ADBManager:
    """
    ADB 管理器
    
    单例模式，全局统一管理 ADB 连接和设备。
    """
    
    def __init__(self):
        self._adb_path: Optional[Path] = None
        self._devices: Dict[str, DeviceInfo] = {}  # serial -> DeviceInfo
        self._device_locks: Dict[str, asyncio.Lock] = {}  # serial -> Lock
        self._initialized = False
        self._server_running = False
        
        # 配置
        self._command_timeout = 30.0  # 秒
        self._retry_count = 3
        self._retry_delay = 1.0  # 秒
        
        logger.info("ADBManager 初始化完成")
    
    # =========================================================================
    # 初始化与清理
    # =========================================================================
    
    async def initialize(self) -> bool:
        """
        初始化 ADB 管理器
        
        Returns:
            是否初始化成功
        """
        if self._initialized:
            return True
        
        logger.info("开始初始化 ADB 管理器...")
        
        # 1. 查找 ADB 可执行文件
        self._adb_path = await self._find_adb_executable()
        if not self._adb_path:
            logger.error("未找到 ADB 可执行文件")
            return False
        
        logger.info(f"使用 ADB: {self._adb_path}")
        
        # 2. 检查 ADB 版本
        version = await self._get_adb_version()
        if not version:
            logger.error("无法获取 ADB 版本")
            return False
        
        logger.info(f"ADB 版本: {version}")
        
        # 3. 启动 ADB server
        if not await self._ensure_server_running():
            logger.error("无法启动 ADB server")
            return False
        
        # 4. 扫描设备
        await self.scan_devices()
        
        self._initialized = True
        logger.info(f"ADB 管理器初始化完成，发现 {len(self._devices)} 个设备")
        return True
    
    async def shutdown(self):
        """关闭 ADB 管理器"""
        logger.info("关闭 ADB 管理器...")
        
        # 清理设备锁
        self._device_locks.clear()
        self._devices.clear()
        
        # 可选：停止 adb server（可能影响其他应用，暂不实施）
        # await self._execute_adb_command(["kill-server"])
        
        self._initialized = False
        logger.info("ADB 管理器已关闭")
    
    # =========================================================================
    # ADB 可执行文件管理
    # =========================================================================
    
    async def _find_adb_executable(self) -> Optional[Path]:
        """
        查找 ADB 可执行文件
        
        查找顺序：
        1. 用户指定路径（Config.ADB_EXECUTABLE）
        2. 应用内置 ADB（Config.ADB_RESOURCES_DIR）
        3. 系统 PATH
        
        Returns:
            ADB 可执行文件路径，未找到返回 None
        """
        # 1. 检查用户指定路径
        custom_path = getattr(Config, 'ADB_EXECUTABLE', None)
        if custom_path:
            path = Path(custom_path)
            if path.exists() and path.is_file():
                if await self._is_valid_adb(path):
                    return path
                logger.warning(f"指定的 ADB 路径无效: {path}")
        
        # 2. 检查应用内置 ADB
        builtin_path = await self._get_builtin_adb_path()
        if builtin_path and builtin_path.exists():
            if await self._is_valid_adb(builtin_path):
                return builtin_path
        
        # 3. 检查系统 PATH
        system_adb = shutil.which("adb")
        if system_adb:
            path = Path(system_adb)
            if await self._is_valid_adb(path):
                logger.info(f"使用系统 ADB: {path}")
                return path
        
        logger.error("未找到可用的 ADB 可执行文件")
        return None
    
    async def _get_builtin_adb_path(self) -> Optional[Path]:
        """
        获取内置 ADB 路径
        
        查找顺序：
        1. Config.ADB_RESOURCES_DIR（若设置）
        2. Config.DATA_DIR/android-adb
        3. 代码所在目录上级的 android-adb（sidecar/源码打包内置）
        """
        system = platform.system()

        def _candidates(base: Path) -> list[Path]:
            # 扁平化目录优先：android-adb/adb 或 android-adb/platform-tools/adb
            candidates = [
                base / "adb",
                base / "adb.exe",
                base / "platform-tools" / "adb",
                base / "platform-tools" / "adb.exe",
            ]
            # 兼容旧版带平台子目录的布局
            if system == "Darwin":
                candidates.append(base / "macos" / "adb")
            elif system == "Windows":
                candidates.append(base / "windows" / "adb.exe")
            elif system == "Linux":
                candidates.append(base / "linux" / "adb")
            else:
                logger.warning(f"不支持的平台: {system}")
            return candidates

        # 1) 用户或配置指定目录
        candidate_dirs = []
        configured = getattr(Config, "ADB_RESOURCES_DIR", None)
        if configured:
            candidate_dirs.append(Path(configured))

        # 2) 默认用户数据目录
        candidate_dirs.append(Config.DATA_DIR / "android-adb")

        # 3) 与代码同层的内置目录（适配 PBS sidecar / 源码运行）
        code_base = Path(__file__).resolve().parents[2]  # .../app/
        candidate_dirs.append(code_base.parent / "android-adb")

        for base in candidate_dirs:
            for adb_path in _candidates(base):
                if adb_path.exists():
                    if system in ["Darwin", "Linux"]:
                        try:
                            adb_path.chmod(0o755)
                        except Exception as e:
                            logger.warning(f"无法添加执行权限: {e}")
                    logger.info(f"使用内置 ADB: {adb_path}")
                    return adb_path

        logger.error("未找到内置 ADB，可设置 Config.ADB_RESOURCES_DIR 指向 android-adb 目录")
        return None
    
    async def _is_valid_adb(self, path: Path) -> bool:
        """
        验证 ADB 可执行文件是否有效
        
        Args:
            path: ADB 路径
        
        Returns:
            是否有效
        """
        try:
            # 执行 adb version 验证
            process = await asyncio.create_subprocess_exec(
                str(path), "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=5.0
            )
            
            if process.returncode == 0 and b"Android Debug Bridge" in stdout:
                return True
            
            logger.warning(f"ADB 验证失败: {path}, 返回码: {process.returncode}")
            return False
            
        except Exception as e:
            logger.warning(f"验证 ADB 时出错: {e}")
            return False
    
    async def _get_adb_version(self) -> Optional[str]:
        """获取 ADB 版本"""
        result = await self._execute_adb_command(["version"])
        if result.success:
            # 解析版本号（第一行通常是 "Android Debug Bridge version x.x.x"）
            lines = result.stdout.strip().split('\n')
            if lines:
                return lines[0].strip()
        return None
    
    # =========================================================================
    # ADB Server 管理
    # =========================================================================
    
    async def _ensure_server_running(self) -> bool:
        """
        确保 ADB server 运行
        
        Returns:
            是否成功
        """
        # 先检查是否已运行
        if await self._check_server_status():
            self._server_running = True
            return True
        
        # 启动 server
        logger.info("启动 ADB server...")
        result = await self._execute_adb_command(["start-server"])
        
        if result.success:
            self._server_running = True
            logger.info("ADB server 启动成功")
            return True
        else:
            logger.error(f"启动 ADB server 失败: {result.stderr}")
            return False
    
    async def _check_server_status(self) -> bool:
        """检查 ADB server 是否运行"""
        result = await self._execute_adb_command(["devices"], timeout=3.0)
        return result.success
    
    # =========================================================================
    # 设备管理
    # =========================================================================
    
    async def scan_devices(self) -> List[DeviceInfo]:
        """
        扫描连接的设备
        
        Returns:
            设备信息列表
        """
        logger.info("扫描 ADB 设备...")
        
        # 执行 adb devices -l 获取详细信息
        result = await self._execute_adb_command(["devices", "-l"])
        if not result.success:
            logger.error(f"扫描设备失败: {result.stderr}")
            return []
        
        # 解析输出
        devices = []
        lines = result.stdout.strip().split('\n')
        
        for line in lines[1:]:  # 跳过第一行 "List of devices attached"
            line = line.strip()
            if not line:
                continue
            
            # 格式: serial status [product:xxx model:xxx device:xxx]
            parts = line.split()
            if len(parts) < 2:
                continue
            
            serial = parts[0]
            status_str = parts[1]
            
            # 解析状态
            try:
                status = DeviceStatus(status_str)
            except ValueError:
                status = DeviceStatus.UNKNOWN
            
            # 解析额外信息
            model = None
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1]
                    break
            
            device_info = DeviceInfo(
                serial=serial,
                status=status,
                model=model,
                last_seen=datetime.now()
            )
            
            devices.append(device_info)
            
            # 更新设备缓存
            if serial in self._devices:
                # 保留锁定状态
                device_info.locked = self._devices[serial].locked
            
            self._devices[serial] = device_info
            
            # 确保设备有锁
            if serial not in self._device_locks:
                self._device_locks[serial] = asyncio.Lock()
        
        logger.info(f"发现 {len(devices)} 个设备")
        return devices
    
    def _is_device_info_complete(self, device: DeviceInfo) -> bool:
        """
        检查设备信息是否完整
        
        关键字段缺失时返回 False，从而触发自动刷新。
        """
        return (
            device.android_version is not None
            and device.screen_width is not None
            and device.screen_height is not None
            and device.screen_density is not None
            and device.battery_level is not None
        )
    
    async def get_device_info(self, serial: str, refresh: bool = False) -> Optional[DeviceInfo]:
        """
        获取设备详细信息
        
        Args:
            serial: 设备序列号
            refresh: 是否强制刷新
        
        Returns:
            设备信息，未找到返回 None
        """
        # 检查缓存
        logger.info(f"检查缓存设备信息: {serial} {refresh}")
        cached_device = self._devices.get(serial)
        if not refresh and cached_device:
            if self._is_device_info_complete(cached_device):
                logger.info(f"使用缓存设备信息: {cached_device}")
                return cached_device
            logger.info("缓存设备信息不完整，自动刷新设备详情")
        
        # 重新扫描
        await self.scan_devices()
        
        if serial not in self._devices:
            logger.warning(f"设备未找到: {serial}")
            return None
        
        device = self._devices[serial]
        device.last_seen = datetime.now()
        
        # 获取详细信息
        try:
            # 屏幕分辨率
            size_result = await self._execute_device_command(
                serial, ["shell", "wm", "size"]
            )
            logger.info(f"屏幕分辨率: {size_result.stdout}")
            if size_result.success:
                # 输出: Physical size: 1080x2400
                import re
                match = re.search(r'(\d+)x(\d+)', size_result.stdout)
                if match:
                    device.screen_width = int(match.group(1))
                    device.screen_height = int(match.group(2))
            
            # 屏幕密度
            density_result = await self._execute_device_command(
                serial, ["shell", "wm", "density"]
            )
            logger.info(f"屏幕密度: {density_result.stdout}")
            if density_result.success:
                # 输出: Physical density: 440
                match = re.search(r'(\d+)', density_result.stdout)
                if match:
                    device.screen_density = int(match.group(1))
            
            # Android 版本
            version_result = await self._execute_device_command(
                serial, ["shell", "getprop", "ro.build.version.release"]
            )
            logger.info(f"Android 版本: {version_result.stdout}")
            if version_result.success:
                device.android_version = version_result.stdout.strip()
            
            # 电池电量
            battery_result = await self._execute_device_command(
                serial, ["shell", "dumpsys", "battery"]
            )
            logger.info(f"电池电量: {battery_result.stdout}")
            if battery_result.success:
                match = re.search(r'level:\s*(\d+)', battery_result.stdout)
                if match:
                    device.battery_level = int(match.group(1))
            
            # 当前应用
            current_app = await self.get_current_app(serial)
            if current_app:
                device.current_app = current_app
            
            logger.info(f"当前应用: {device.current_app}")
            # 更新缓存
            self._devices[serial] = device
            logger.info(f"设备信息: {device}")
            
        except Exception as e:
            logger.warning(f"获取设备详细信息失败: {e}")
        
        return device
    
    async def get_current_app(self, serial: str) -> Optional[str]:
        """
        获取当前前台应用包名
        
        使用多种方法以确保在不同 Android 版本下的兼容性：
        1. dumpsys activity activities (Android 5.0+) - 最可靠
        2. dumpsys window windows (Android 4.0+) - 备用方案
        
        Args:
            serial: 设备序列号
        
        Returns:
            应用包名，失败返回 None
        """
        import re
        
        # 方法 1: dumpsys activity activities (推荐，最兼容)
        # 获取 mResumedActivity 或 mFocusedActivity
        result = await self._execute_device_command(
            serial,
            ["shell", "dumpsys activity activities"]
        )
        
        if result.success:
            # 在 Python 中搜索相关行（不使用管道，确保兼容性）
            for line in result.stdout.split('\n'):
                # Android 5.0+: mResumedActivity
                if 'mResumedActivity' in line:
                    # 格式: mResumedActivity: ActivityRecord{xxx u0 com.example.app/.MainActivity t123}
                    match = re.search(r'([a-zA-Z0-9._]+)/([a-zA-Z0-9._$.]+)', line)
                    if match:
                        return match.group(1)
                
                # Android 8.0+: mFocusedActivity
                if 'mFocusedActivity' in line:
                    match = re.search(r'([a-zA-Z0-9._]+)/([a-zA-Z0-9._$.]+)', line)
                    if match:
                        return match.group(1)
        
        # 方法 2: dumpsys window windows (备用方案)
        result = await self._execute_device_command(
            serial,
            ["shell", "dumpsys window windows"]
        )
        
        if result.success:
            for line in result.stdout.split('\n'):
                # mCurrentFocus 或 mFocusedApp
                if 'mCurrentFocus' in line or 'mFocusedApp' in line:
                    # 格式: mCurrentFocus=Window{abc u0 com.example.app/com.example.MainActivity}
                    match = re.search(r'([a-zA-Z0-9._]+)/([a-zA-Z0-9._$.]+)', line)
                    if match:
                        return match.group(1)
        
        logger.debug(f"无法检测设备 {serial} 的当前应用")
        return None
    
    def list_devices(self, online_only: bool = True) -> List[DeviceInfo]:
        """
        列出设备
        
        Args:
            online_only: 是否仅列出在线设备
        
        Returns:
            设备列表
        """
        devices = list(self._devices.values())
        
        if online_only:
            devices = [d for d in devices if d.status == DeviceStatus.ONLINE]
        
        return devices
    
    async def lock_device(self, serial: str) -> bool:
        """
        锁定设备（用于任务执行）
        
        Args:
            serial: 设备序列号
        
        Returns:
            是否成功锁定
        """
        if serial not in self._devices:
            logger.warning(f"设备不存在: {serial}")
            return False
        
        if serial not in self._device_locks:
            self._device_locks[serial] = asyncio.Lock()
        
        # 尝试立即获取锁（非阻塞）
        locked = self._device_locks[serial].locked()
        if locked:
            logger.warning(f"设备已被锁定: {serial}")
            return False
        
        await self._device_locks[serial].acquire()
        self._devices[serial].locked = True
        logger.info(f"设备已锁定: {serial}")
        return True
    
    def unlock_device(self, serial: str):
        """
        解锁设备
        
        Args:
            serial: 设备序列号
        """
        if serial in self._device_locks and self._device_locks[serial].locked():
            self._device_locks[serial].release()
            if serial in self._devices:
                self._devices[serial].locked = False
            logger.info(f"设备已解锁: {serial}")
    
    # =========================================================================
    # 命令执行
    # =========================================================================
    
    async def _execute_adb_command(
        self,
        args: List[str],
        timeout: Optional[float] = None
    ) -> CommandResult:
        """
        执行 ADB 命令（不指定设备）
        
        Args:
            args: 命令参数（不包含 adb）
            timeout: 超时时间（秒）
        
        Returns:
            命令执行结果
        """
        if not self._adb_path:
            return CommandResult(
                success=False,
                stdout="",
                stderr="ADB not initialized",
                return_code=-1,
                duration_ms=0,
                command=" ".join(args)
            )
        
        timeout = timeout or self._command_timeout
        command = [str(self._adb_path)] + args
        command_str = " ".join(command)
        
        start_time = time.time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            return_code = process.returncode if process.returncode is not None else -1
            result = CommandResult(
                success=return_code == 0,
                stdout=stdout.decode('utf-8', errors='ignore'),
                stderr=stderr.decode('utf-8', errors='ignore'),
                return_code=return_code,
                duration_ms=duration_ms,
                command=command_str
            )
            
            if result.success:
                logger.debug(f"命令执行成功: {command_str} ({duration_ms:.2f}ms)")
            else:
                logger.warning(f"命令执行失败: {command_str}, 错误: {result.stderr}")
            
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"命令超时: {command_str}")
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Timeout after {timeout}s",
                return_code=-1,
                duration_ms=(time.time() - start_time) * 1000,
                command=command_str
            )
        except Exception as e:
            logger.error(f"命令执行异常: {command_str}, 错误: {e}")
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                duration_ms=(time.time() - start_time) * 1000,
                command=command_str
            )
    
    async def _execute_device_command(
        self,
        serial: str,
        args: List[str],
        timeout: Optional[float] = None,
        retry: bool = True
    ) -> CommandResult:
        """
        执行设备相关命令（自动添加 -s serial）
        
        Args:
            serial: 设备序列号
            args: 命令参数
            timeout: 超时时间
            retry: 是否自动重试
        
        Returns:
            命令执行结果
        """
        full_args = ["-s", serial] + args
        
        if not retry:
            return await self._execute_adb_command(full_args, timeout)
        
        # 重试逻辑
        for attempt in range(self._retry_count):
            result = await self._execute_adb_command(full_args, timeout)
            
            if result.success:
                return result
            
            if attempt < self._retry_count - 1:
                logger.warning(f"命令失败，{self._retry_delay}秒后重试... (尝试 {attempt + 1}/{self._retry_count})")
                await asyncio.sleep(self._retry_delay)
        
        return result
    
    async def execute_command(
        self,
        serial: str,
        command_type: str,
        args: List[str],
        timeout: Optional[float] = None
    ) -> CommandResult:
        """
        执行 ADB 命令（公开接口）
        
        用于外部调用执行设备命令。
        
        Args:
            serial: 设备序列号
            command_type: 命令类型（如 "shell", "push", "pull"）
            args: 命令参数
            timeout: 超时时间（秒）
        
        Returns:
            命令执行结果
        
        示例:
            # 执行 shell 命令
            result = await adb_manager.execute_command("xxx", "shell", ["echo", "hello"])
            
            # 预热连接
            result = await adb_manager.execute_command("xxx", "shell", ["echo", "warmup"])
        """
        full_args = [command_type] + args
        return await self._execute_device_command(serial, full_args, timeout)
    
    # =========================================================================
    # 坐标系统转换
    # =========================================================================
    
    def normalize_coordinates(
        self,
        x: int,
        y: int,
        screen_width: int,
        screen_height: int
    ) -> Tuple[int, int]:
        """
        将绝对坐标转换为归一化坐标 (0-1000)
        
        Args:
            x: 绝对 x 坐标
            y: 绝对 y 坐标
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
        
        Returns:
            归一化坐标 (x, y)
        """
        norm_x = int((x / screen_width) * 1000)
        norm_y = int((y / screen_height) * 1000)
        
        # 边界检查
        norm_x = max(0, min(1000, norm_x))
        norm_y = max(0, min(1000, norm_y))
        
        return norm_x, norm_y
    
    def denormalize_coordinates(
        self,
        norm_x: int,
        norm_y: int,
        screen_width: int,
        screen_height: int
    ) -> Tuple[int, int]:
        """
        将归一化坐标 (0-1000) 转换为绝对坐标
        
        Args:
            norm_x: 归一化 x 坐标
            norm_y: 归一化 y 坐标
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
        
        Returns:
            绝对坐标 (x, y)
        """
        x = int((norm_x / 1000) * screen_width)
        y = int((norm_y / 1000) * screen_height)
        
        # 边界检查
        x = max(0, min(screen_width - 1, x))
        y = max(0, min(screen_height - 1, y))
        
        return x, y
    
    # =========================================================================
    # 配置管理
    # =========================================================================
    
    def set_command_timeout(self, timeout: float):
        """设置命令超时时间"""
        self._command_timeout = timeout
        logger.info(f"命令超时时间设置为: {timeout}秒")
    
    def set_retry_count(self, count: int):
        """设置重试次数"""
        self._retry_count = count
        logger.info(f"重试次数设置为: {count}")
    
    def get_adb_path(self) -> Optional[Path]:
        """获取 ADB 可执行文件路径"""
        return self._adb_path


# =============================================================================
# 单例管理
# =============================================================================

_adb_manager_instance: Optional[ADBManager] = None


def get_adb_manager() -> ADBManager:
    """获取 ADB 管理器单例"""
    global _adb_manager_instance
    if _adb_manager_instance is None:
        _adb_manager_instance = ADBManager()
    return _adb_manager_instance
