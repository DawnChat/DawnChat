"""
DawnChat - MLX Server 进程管理器
负责 mlx-lm / mlx-vlm server 的生命周期管理、健康检查、自动重启等
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path
import platform
import socket
import subprocess
from typing import Dict, List, Optional

from app.config import Config
from app.utils.logger import setup_logger

logger = setup_logger("dawnchat.mlx_server", log_file=Config.LOGS_DIR / "mlx.log")


@dataclass(frozen=True)
class MLXServerEndpoints:
    lm_api_base: str
    vlm_api_base: str


class _BaseProcessManager:
    def __init__(self, name: str, port: int, log_file: Path):
        self._name = name
        self._port = port
        self._log_file = log_file
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.crash_history: List[datetime] = []
        self._health_check_task: Optional[asyncio.Task] = None
        self._start_lock: asyncio.Lock = asyncio.Lock()

    def _is_port_in_use(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                return result == 0
        except Exception as e:
            logger.warning("检查端口 %s 时出错: %s", port, e)
            return False

    def _try_kill_port_process(self, port: int) -> bool:
        try:
            if platform.system() == "Windows":
                return False
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        if self.process and str(self.process.pid) == str(pid):
                            logger.info(
                                "%s 端口 %s 当前由本进程占用 (PID: %s)，跳过清理",
                                self._name,
                                port,
                                pid,
                            )
                            continue
                        logger.info("终止占用端口 %s 的进程 PID: %s", port, pid)
                        subprocess.run(["kill", "-9", pid], timeout=5)
                    except Exception as e:
                        logger.warning("无法终止进程 %s: %s", pid, e)
                import time

                time.sleep(1)
                return not self._is_port_in_use(port)
            return False
        except Exception as e:
            logger.warning("清理端口 %s 时出错: %s", port, e)
            return False

    def _record_crash(self):
        now = datetime.now()
        self.crash_history.append(now)
        cutoff = now - timedelta(seconds=Config.CRASH_DETECTION_WINDOW)
        self.crash_history = [t for t in self.crash_history if t > cutoff]
        logger.warning(
            "%s 崩溃历史: 最近 %s 秒内崩溃 %s 次",
            self._name,
            Config.CRASH_DETECTION_WINDOW,
            len(self.crash_history),
        )

    def _should_restart(self) -> bool:
        return len(self.crash_history) < Config.CRASH_MAX_COUNT

    async def stop(self, force: bool = False) -> bool:
        if not self.is_running or not self.process:
            return True

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        if force:
            await self._kill_process()
        else:
            await self._terminate_process()

        self.is_running = False
        self.process = None
        return True

    async def _terminate_process(self):
        if not self.process:
            return
        try:
            self.process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self.process.wait),
                    timeout=Config.SHUTDOWN_TIMEOUT,
                )
            except asyncio.TimeoutError:
                await self._kill_process()
        except Exception:
            await self._kill_process()

    async def _kill_process(self):
        if not self.process:
            return
        try:
            self.process.kill()
            await asyncio.to_thread(self.process.wait)
        except Exception:
            pass

    async def _perform_health_check(self, health_url: str) -> bool:
        import requests

        for attempt in range(1, Config.HEALTH_CHECK_MAX_RETRIES + 1):
            if self.process and self.process.poll() is not None:
                logger.error("%s 进程已退出，退出码: %s", self._name, self.process.returncode)
                return False
            try:
                def sync_check():
                    return requests.get(health_url, timeout=Config.HEALTH_CHECK_TIMEOUT)

                resp = await asyncio.to_thread(sync_check)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            if attempt < Config.HEALTH_CHECK_MAX_RETRIES:
                await asyncio.sleep(1)
        return False

    async def _health_check_loop(self, health_url: str, restart_cb):
        while self.is_running:
            try:
                await asyncio.sleep(Config.HEALTH_CHECK_INTERVAL)
                if self.process and self.process.poll() is not None:
                    logger.error("%s 进程崩溃 (退出码: %s)", self._name, self.process.returncode)
                    self._record_crash()
                    if self._should_restart():
                        logger.info("%s 尝试自动重启...", self._name)
                        self.is_running = False
                        self.process = None
                        if await restart_cb():
                            logger.info("%s 自动重启成功", self._name)
                        else:
                            logger.error("%s 自动重启失败", self._name)
                            self.is_running = False
                            break
                    else:
                        logger.error("%s 崩溃次数过多，停止自动重启", self._name)
                        self.is_running = False
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("%s 健康检查循环异常: %s", self._name, e, exc_info=True)


class MLXLMServerManager(_BaseProcessManager):
    def __init__(self):
        super().__init__(
            name="mlx-lm",
            port=Config.MLX_LM_SERVER_PORT,
            log_file=Config.LOGS_DIR / "mlx_lm.log",
        )
        self.current_model_path: Optional[Path] = None

    def get_api_base(self) -> str:
        return f"http://127.0.0.1:{self._port}/v1"

    async def start_with_model(self, model_path: Path) -> bool:
        async with self._start_lock:
            if (
                self.is_running
                and self.process
                and self.process.poll() is None
                and self.current_model_path == model_path
            ):
                return True

            if self.is_running:
                await self.stop()

        if not model_path.exists():
            logger.error("MLX-LM 模型路径不存在: %s", model_path)
            return False

        if self._is_port_in_use(self._port):
            health_url = f"http://127.0.0.1:{self._port}/health"
            ok = await self._perform_health_check(health_url)
            if ok:
                logger.info("检测到已有 mlx-lm 服务存活，复用现有进程")
                self.current_model_path = model_path
                self.is_running = True
                return True
            logger.warning("mlx-lm 端口 %s 被占用且健康检查失败，尝试清理...", self._port)
            self._try_kill_port_process(self._port)

        for attempt in range(1, Config.STARTUP_MAX_RETRIES + 1):
            logger.info(
                "尝试启动 mlx-lm (第 %s/%s 次), model=%s",
                attempt,
                Config.STARTUP_MAX_RETRIES,
                model_path,
            )
            ok = await self._start_process(model_path)
            if ok:
                self.current_model_path = model_path
                self.is_running = True
                health_url = f"http://127.0.0.1:{self._port}/health"
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop(
                        health_url, restart_cb=lambda: self._restart_current_model()
                    )
                )
                return True
            if attempt < Config.STARTUP_MAX_RETRIES:
                await asyncio.sleep(Config.STARTUP_RETRY_DELAY)

        return False

    async def _restart_current_model(self) -> bool:
        if not self.current_model_path:
            return False
        return await self.start_with_model(self.current_model_path)

    async def _start_process(self, model_path: Path) -> bool:
        python = Config.get_pbs_python()
        if not python:
            logger.error("无法找到可用的 Python 运行时")
            return False

        cmd = [
            str(python),
            "-m",
            "mlx_lm.server",
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--log-level",
            "INFO",
        ]

        env = os.environ.copy()
        env.setdefault("HF_HOME", str(Config.HF_CACHE_DIR))
        env.setdefault("TRANSFORMERS_CACHE", str(Config.HF_CACHE_DIR))

        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(self._log_file, "a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(Config.BACKEND_ROOT),
                env=env,
                stdout=log_fp,
                stderr=log_fp,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error("启动 mlx-lm 失败: %s", e, exc_info=True)
            self.process = None
            return False
        finally:
            try:
                log_fp.close()
            except Exception:
                pass

        health_url = f"http://127.0.0.1:{self._port}/health"
        ok = await self._perform_health_check(health_url)
        if not ok:
            await self._kill_process()
            self.process = None
            return False
        return True

    async def stop(self, force: bool = False) -> bool:
        await super().stop(force=force)
        self.current_model_path = None
        return True

    def get_status(self) -> Dict:
        return {
            "name": self._name,
            "is_running": self.is_running,
            "pid": self.process.pid if self.process else None,
            "port": self._port,
            "api_base": self.get_api_base(),
            "current_model": str(self.current_model_path) if self.current_model_path else None,
            "crash_count": len(self.crash_history),
        }


class MLXVLMServerManager(_BaseProcessManager):
    def __init__(self):
        super().__init__(
            name="mlx-vlm",
            port=Config.MLX_VLM_SERVER_PORT,
            log_file=Config.LOGS_DIR / "mlx_vlm.log",
        )

    def get_api_base(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    async def ensure_started(self) -> bool:
        async with self._start_lock:
            if self.is_running and self.process and self.process.poll() is None:
                return True

        if self._is_port_in_use(self._port):
            health_url = f"http://127.0.0.1:{self._port}/health"
            ok = await self._perform_health_check(health_url)
            if ok:
                logger.info("检测到已有 mlx-vlm 服务存活，复用现有进程")
                self.is_running = True
                return True
            logger.warning("mlx-vlm 端口 %s 被占用且健康检查失败，尝试清理...", self._port)
            self._try_kill_port_process(self._port)

        for attempt in range(1, Config.STARTUP_MAX_RETRIES + 1):
            logger.info("尝试启动 mlx-vlm (第 %s/%s 次)", attempt, Config.STARTUP_MAX_RETRIES)
            ok = await self._start_process()
            if ok:
                self.is_running = True
                health_url = f"http://127.0.0.1:{self._port}/health"
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop(health_url, restart_cb=lambda: self.ensure_started())
                )
                return True
            if attempt < Config.STARTUP_MAX_RETRIES:
                await asyncio.sleep(Config.STARTUP_RETRY_DELAY)
        return False

    async def _start_process(self) -> bool:
        python = Config.get_pbs_python()
        if not python:
            logger.error("无法找到可用的 Python 运行时")
            return False

        cmd = [
            str(python),
            "-m",
            "uvicorn",
            "mlx_vlm.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self._port),
            "--workers",
            "1",
        ]

        env = os.environ.copy()
        env.setdefault("HF_HOME", str(Config.HF_CACHE_DIR))
        env.setdefault("TRANSFORMERS_CACHE", str(Config.HF_CACHE_DIR))

        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fp = open(self._log_file, "a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(Config.BACKEND_ROOT),
                env=env,
                stdout=log_fp,
                stderr=log_fp,
                stdin=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error("启动 mlx-vlm 失败: %s", e, exc_info=True)
            self.process = None
            return False
        finally:
            try:
                log_fp.close()
            except Exception:
                pass

        health_url = f"http://127.0.0.1:{self._port}/health"
        ok = await self._perform_health_check(health_url)
        if not ok:
            await self._kill_process()
            self.process = None
            return False
        return True

    def get_status(self) -> Dict:
        return {
            "name": self._name,
            "is_running": self.is_running,
            "pid": self.process.pid if self.process else None,
            "port": self._port,
            "api_base": self.get_api_base(),
            "crash_count": len(self.crash_history),
        }


class MLXServerManager:
    _instance: Optional["MLXServerManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.lm = MLXLMServerManager()
        self.vlm = MLXVLMServerManager()
        logger.info("MLX Server 管理器已初始化")

    async def ensure_lm_ready(self, model_path: Path) -> bool:
        return await self.lm.start_with_model(model_path)

    async def ensure_vlm_ready(self) -> bool:
        return await self.vlm.ensure_started()

    def get_endpoints(self) -> MLXServerEndpoints:
        return MLXServerEndpoints(
            lm_api_base=self.lm.get_api_base(),
            vlm_api_base=self.vlm.get_api_base(),
        )

    def get_status(self) -> Dict:
        return {"lm": self.lm.get_status(), "vlm": self.vlm.get_status()}


_mlx_server_manager: Optional[MLXServerManager] = None


def get_mlx_server_manager() -> MLXServerManager:
    global _mlx_server_manager
    if _mlx_server_manager is None:
        _mlx_server_manager = MLXServerManager()
    return _mlx_server_manager
