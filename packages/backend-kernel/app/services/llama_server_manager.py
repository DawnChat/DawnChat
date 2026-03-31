"""
DawnChat - Llama Server 进程管理器
负责 llama-server 进程的生命周期管理、健康检查、自动重启等
"""

import asyncio
from datetime import datetime, timedelta
import os
from pathlib import Path
import platform
import socket
import subprocess
from typing import Any, Dict, List, Optional

from app.config import Config
from app.services.llama_binary_manager import get_binary_manager
from app.services.model_manager import find_mmproj_for_model
from app.utils.logger import setup_logger

logger = setup_logger("dawnchat.llama_server", log_file=Config.LOGS_DIR / "llama.log")


class LlamaServerManager:
    """
    Llama Server 进程管理器
    
    职责：
    1. 启动/停止 llama-server 进程
    2. 健康检查
    3. 模型加载（通过启动参数）
    4. 崩溃检测与自动重启
    """
    
    _instance: Optional['LlamaServerManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.is_running = False
        self.current_model_path: Optional[Path] = None
        self.current_mmproj_path: Optional[Path] = None  # 视觉模型的 mmproj 文件路径
        self.current_context_size: int = Config.LLAMA_SERVER_DEFAULT_CONTEXT
        self.current_gpu_layers: int = Config.LLAMA_SERVER_DEFAULT_GPU_LAYERS
        self.crash_history: List[datetime] = []
        self._health_check_task: Optional[asyncio.Task[None]] = None
        self._binary_manager = get_binary_manager()
        self._port = Config.LLAMA_SERVER_PORT
        
        logger.info("Llama Server 管理器已初始化")
    
    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('127.0.0.1', port))
                return result == 0
        except Exception as e:
            logger.warning(f"检查端口 {port} 时出错: {e}")
            return False
    
    def _try_kill_port_process(self, port: int) -> bool:
        """尝试终止占用指定端口的进程"""
        try:
            if platform.system() == "Windows":
                # Windows 使用 netstat + taskkill
                result = subprocess.run(
                    ['netstat', '-ano', '|', 'findstr', f':{port}'],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=5
                )
                # 解析 PID 并终止
                # 这里简化处理
                return False
            else:
                # macOS/Linux 使用 lsof
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid in pids:
                        try:
                            logger.info(f"终止占用端口 {port} 的进程 PID: {pid}")
                            subprocess.run(['kill', '-9', pid], timeout=5)
                        except Exception as e:
                            logger.warning(f"无法终止进程 {pid}: {e}")
                    
                    # 等待端口释放
                    import time
                    time.sleep(1)
                    return not self._is_port_in_use(port)
            
            return False
        except Exception as e:
            logger.warning(f"清理端口 {port} 时出错: {e}")
            return False
    
    def _build_command(self, model_path: Path, mmproj_path: Optional[Path] = None) -> List[str]:
        """
        构建 llama-server 启动命令
        
        Args:
            model_path: 模型文件路径
            mmproj_path: mmproj 文件路径（视觉模型需要）
        
        Returns:
            命令列表
        """
        executable = Config.get_llama_server_executable()
        
        cmd = [
            str(executable),
            "-m", str(model_path),
            "--port", str(self._port),
            "--host", "127.0.0.1",
            "-c", str(self.current_context_size),
            "-ngl", str(self.current_gpu_layers),
            "--log-disable",  # 禁用文件日志
        ]
        
        if "embedding" in str(model_path).lower():
            cmd.append("--embeddings")

        # 如果有 mmproj 文件（视觉模型），添加 --mmproj 参数
        if mmproj_path and mmproj_path.exists():
            cmd.extend(["--mmproj", str(mmproj_path)])
            logger.info(f"📷 加载视觉投影文件: {mmproj_path.name}")
        
        # macOS Metal 优化
        if platform.system() == "Darwin":
            cpu_count = os.cpu_count() or 8
            cmd.extend(["--threads", str(cpu_count)])
        
        return cmd
    
    async def start_with_model(
        self, 
        model_path: Path,
        context_size: Optional[int] = None,
        gpu_layers: Optional[int] = None
    ) -> bool:
        """
        使用指定模型启动 llama-server
        
        对于视觉模型，会自动检测并加载同目录下的 mmproj 文件。
        
        Args:
            model_path: GGUF 模型文件路径
            context_size: 上下文窗口大小（可选）
            gpu_layers: GPU 层数（可选，-1=全部）
        
        Returns:
            是否启动成功
        """
        import time
        start_time = time.time()
        
        # 如果已运行相同模型，直接返回
        if self.is_running and self.process and self.current_model_path == model_path:
            logger.info(f"llama-server 已在运行相同模型: {model_path.name}")
            return True
        
        # 如果运行的是不同模型，先停止
        if self.is_running:
            logger.info("停止当前运行的 llama-server 以切换模型...")
            await self.stop()
        
        # 验证模型文件
        if not model_path.exists():
            logger.error(f"模型文件不存在: {model_path}")
            return False
        
        # 确保二进制可用
        binary_path = await self._binary_manager.ensure_binary()
        if not binary_path:
            logger.error("llama-server 二进制不可用")
            return False
        
        # 更新配置
        self.current_model_path = model_path
        if context_size:
            self.current_context_size = context_size
        if gpu_layers is not None:
            self.current_gpu_layers = gpu_layers
        
        # 自动检测 mmproj 文件（视觉模型需要）
        self.current_mmproj_path = find_mmproj_for_model(model_path)
        if self.current_mmproj_path:
            logger.info(f"📷 检测到视觉模型，将加载 mmproj: {self.current_mmproj_path.name}")
        
        # 检查端口
        if self._is_port_in_use(self._port):
            logger.warning(f"端口 {self._port} 被占用，尝试清理...")
            if not self._try_kill_port_process(self._port):
                logger.error(f"无法清理端口 {self._port}")
                # 继续尝试，可能是残留进程
        
        # 启动进程
        for attempt in range(1, Config.STARTUP_MAX_RETRIES + 1):
            logger.info(f"尝试启动 llama-server (第 {attempt}/{Config.STARTUP_MAX_RETRIES} 次)")
            logger.info(f"  模型: {model_path.name}")
            logger.info(f"  上下文: {self.current_context_size}")
            logger.info(f"  GPU 层: {self.current_gpu_layers}")
            if self.current_mmproj_path:
                logger.info(f"  视觉投影: {self.current_mmproj_path.name}")
            
            success = await self._start_process()
            
            if success:
                # 启动健康检查循环
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                total_time = int((time.time() - start_time) * 1000)
                logger.info(f"✅ llama-server 启动成功 (耗时: {total_time}ms)")
                return True
            
            if attempt < Config.STARTUP_MAX_RETRIES:
                logger.warning(f"启动失败，{Config.STARTUP_RETRY_DELAY} 秒后重试...")
                await asyncio.sleep(Config.STARTUP_RETRY_DELAY)
        
        logger.error(f"llama-server 启动失败，已重试 {Config.STARTUP_MAX_RETRIES} 次")
        return False
    
    async def _start_process(self) -> bool:
        """启动 llama-server 进程"""
        try:
            if not self.current_model_path:
                logger.error("未设置模型路径，无法启动 llama-server")
                return False
            cmd = self._build_command(self.current_model_path, self.current_mmproj_path)
            
            logger.info(f"执行命令: {' '.join(cmd)}")
            
            # 设置环境变量
            env = os.environ.copy()
            
            # macOS 需要设置动态库路径
            if platform.system() == "Darwin":
                bin_dir = str(Config.BIN_DIR)
                if 'DYLD_LIBRARY_PATH' in env:
                    env['DYLD_LIBRARY_PATH'] = f"{bin_dir}:{env['DYLD_LIBRARY_PATH']}"
                else:
                    env['DYLD_LIBRARY_PATH'] = bin_dir
            
            # 启动进程
            self.process = subprocess.Popen(
                cmd,
                cwd=str(Config.BIN_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL
            )
            
            # 等待进程启动（模型加载需要时间）
            logger.info("等待 llama-server 加载模型...")
            
            # 执行健康检查
            if await self._perform_health_check():
                self.is_running = True
                logger.info(f"llama-server 进程已启动，PID: {self.process.pid}")
                return True
            else:
                logger.error("llama-server 启动但健康检查失败")
                
                # 尝试获取错误输出
                if self.process:
                    try:
                        stdout, stderr = self.process.communicate(timeout=1)
                        if stderr:
                            logger.error(f"进程错误输出: {stderr.decode('utf-8', errors='ignore')[:500]}")
                    except subprocess.TimeoutExpired:
                        pass
                    except Exception:
                        pass
                
                await self._kill_process()
                return False
                
        except FileNotFoundError:
            logger.error(f"llama-server 可执行文件不存在: {Config.get_llama_server_executable()}")
            return False
        except Exception as e:
            logger.error(f"启动 llama-server 时发生异常: {e}", exc_info=True)
            return False
    
    async def stop(self, force: bool = False) -> bool:
        """
        停止 llama-server 服务
        
        Args:
            force: 是否强制终止
        
        Returns:
            是否停止成功
        """
        if not self.is_running or not self.process:
            logger.info("llama-server 未运行")
            return True
        
        # 停止健康检查任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        
        # 停止进程
        if force:
            logger.info("强制终止 llama-server 进程")
            await self._kill_process()
        else:
            logger.info("优雅地关闭 llama-server 进程")
            await self._terminate_process()
        
        self.is_running = False
        self.process = None
        self.current_model_path = None
        self.current_mmproj_path = None
        logger.info("llama-server 已停止")
        return True
    
    async def _terminate_process(self):
        """优雅地终止进程（SIGTERM -> SIGKILL）"""
        if not self.process:
            return
        
        try:
            logger.debug(f"向 llama-server (PID: {self.process.pid}) 发送 SIGTERM")
            self.process.terminate()
            
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self.process.wait),
                    timeout=Config.SHUTDOWN_TIMEOUT
                )
                logger.debug("llama-server 已优雅退出")
            except asyncio.TimeoutError:
                logger.warning(f"进程在 {Config.SHUTDOWN_TIMEOUT} 秒内未退出，发送 SIGKILL")
                await self._kill_process()
        except Exception as e:
            logger.error(f"终止进程时发生异常: {e}", exc_info=True)
            await self._kill_process()
    
    async def _kill_process(self):
        """强制杀死进程（SIGKILL）"""
        if not self.process:
            return
        
        try:
            logger.debug(f"向 llama-server (PID: {self.process.pid}) 发送 SIGKILL")
            self.process.kill()
            await asyncio.to_thread(self.process.wait)
            logger.debug("llama-server 已被强制终止")
        except Exception as e:
            logger.error(f"杀死进程时发生异常: {e}", exc_info=True)
    
    async def _perform_health_check(self) -> bool:
        """执行健康检查（使用 /health 端点）"""
        import importlib
        requests = importlib.import_module("requests")
        
        health_url = f"http://127.0.0.1:{self._port}/health"
        logger.info(f"开始健康检查: {health_url}")
        
        for attempt in range(1, Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES + 1):
            # 首先检查进程是否还在运行
            if self.process and self.process.poll() is not None:
                logger.error(f"进程已退出，退出码: {self.process.returncode}")
                return False
            
            try:
                def sync_check():
                    return requests.get(health_url, timeout=Config.HEALTH_CHECK_TIMEOUT)
                
                response = await asyncio.to_thread(sync_check)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        status = data.get("status", "unknown")
                        if status == "ok":
                            logger.info(f"✅ 健康检查成功 (第 {attempt} 次)")
                            return True
                        elif status == "loading model":
                            logger.info(f"模型加载中... (第 {attempt}/{Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES} 次)")
                        else:
                            logger.warning(f"未知状态: {status}")
                    except ValueError:
                        # 如果返回 200 但不是 JSON，也认为是健康的
                        logger.info("✅ 健康检查成功 (非 JSON 响应)")
                        return True
                else:
                    logger.warning(f"健康检查返回状态码: {response.status_code}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"健康检查超时 (第 {attempt}/{Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES} 次)")
            except requests.exceptions.ConnectionError:
                logger.warning(f"连接失败 (第 {attempt}/{Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES} 次)")
            except Exception as e:
                logger.warning(f"健康检查异常: {e}")
            
            if attempt < Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES:
                await asyncio.sleep(2)
        
        logger.error(f"❌ 健康检查失败，已尝试 {Config.LLAMA_SERVER_HEALTH_CHECK_RETRIES} 次")
        return False
    
    async def _health_check_loop(self):
        """后台健康检查循环"""
        logger.info("启动健康检查循环")
        
        while self.is_running:
            try:
                await asyncio.sleep(Config.HEALTH_CHECK_INTERVAL)
                
                # 检查进程是否存活
                if self.process and self.process.poll() is not None:
                    logger.error(f"检测到 llama-server 进程崩溃 (退出码: {self.process.returncode})")
                    self._record_crash()
                    
                    if self._should_restart():
                        logger.info("尝试自动重启...")
                        if self.current_model_path and await self.start_with_model(self.current_model_path):
                            logger.info("自动重启成功")
                        else:
                            logger.error("自动重启失败")
                            self.is_running = False
                            break
                    else:
                        logger.error("崩溃次数过多，停止自动重启")
                        self.is_running = False
                        break
                
            except asyncio.CancelledError:
                logger.info("健康检查循环被取消")
                break
            except Exception as e:
                logger.error(f"健康检查循环发生异常: {e}", exc_info=True)
    
    def _record_crash(self):
        """记录崩溃事件"""
        now = datetime.now()
        self.crash_history.append(now)
        
        cutoff = now - timedelta(seconds=Config.CRASH_DETECTION_WINDOW)
        self.crash_history = [t for t in self.crash_history if t > cutoff]
        
        logger.warning(f"崩溃历史: 最近 {Config.CRASH_DETECTION_WINDOW} 秒内崩溃 {len(self.crash_history)} 次")
    
    def _should_restart(self) -> bool:
        """判断是否应该重启"""
        recent_crashes = len(self.crash_history)
        return recent_crashes < Config.CRASH_MAX_COUNT
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态信息"""
        return {
            "is_running": self.is_running,
            "pid": self.process.pid if self.process else None,
            "current_model": self.current_model_path.name if self.current_model_path else None,
            "current_mmproj": self.current_mmproj_path.name if self.current_mmproj_path else None,
            "has_vision": self.current_mmproj_path is not None,
            "context_size": self.current_context_size,
            "gpu_layers": self.current_gpu_layers,
            "port": self._port,
            "api_base": f"http://127.0.0.1:{self._port}/v1",
            "crash_count": len(self.crash_history),
        }
    
    def get_api_base(self) -> str:
        """获取 API 基础 URL"""
        return f"http://127.0.0.1:{self._port}/v1"


# 全局单例
_server_manager: Optional[LlamaServerManager] = None


def get_server_manager() -> LlamaServerManager:
    """获取 Llama Server 管理器单例"""
    global _server_manager
    if _server_manager is None:
        _server_manager = LlamaServerManager()
    return _server_manager
