"""
OpenCode 进程管理器

职责：
1. 启动/停止 OpenCode Server 进程
2. 健康检查与自动重启
3. 启动基线配置注入（OPENCODE_CONFIG_CONTENT）
4. 运行时配置与信息透传（/config、/config/providers、/agent）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import platform
import subprocess
from typing import Any, Dict, List, Optional

import httpx

from app.config import Config
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.services.opencode_baseline_config_composer import OpenCodeBaselineConfigComposer
from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("opencode_manager")


class OpenCodeUnavailableError(RuntimeError):
    """OpenCode 进程不可用或无法连通。"""


class OpenCodeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class OpenCodeStats:
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    health_check_failures: int = 0
    restart_count: int = 0


class OpenCodeManager:
    def __init__(self) -> None:
        self._process: Optional[asyncio.subprocess.Process] = None
        self._status = OpenCodeStatus.STOPPED
        self._stats = OpenCodeStats()
        self._http_client: Optional[httpx.AsyncClient] = None
        self._health_client: Optional[httpx.AsyncClient] = None
        self._health_check_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()
        self._stopping = False
        self._workspace_path: Optional[Path] = None
        self._startup_context: Dict[str, Any] = {}
        self._instruction_policy: Dict[str, Any] = {}
        self._baseline_config_composer = OpenCodeBaselineConfigComposer()
        self._last_start_failure: Optional[Dict[str, Any]] = None

    @property
    def status(self) -> OpenCodeStatus:
        return self._status

    @property
    def stats(self) -> OpenCodeStats:
        return self._stats

    @property
    def host(self) -> str:
        return Config.OPENCODE_HOST

    @property
    def port(self) -> int:
        return Config.OPENCODE_PORT

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def is_running(self) -> bool:
        return self._status == OpenCodeStatus.RUNNING

    @property
    def workspace_path(self) -> Optional[str]:
        return str(self._workspace_path) if self._workspace_path else None

    @property
    def startup_context(self) -> Dict[str, Any]:
        return dict(self._startup_context)

    @property
    def last_start_failure(self) -> Optional[Dict[str, Any]]:
        return dict(self._last_start_failure) if isinstance(self._last_start_failure, dict) else None

    async def start(
        self,
        workspace_path: str,
        force_restart: bool = False,
        startup_context: Optional[Dict[str, Any]] = None,
        instruction_policy: Optional[Dict[str, Any]] = None,
    ) -> bool:
        async with self._lock:
            target_workspace = self._resolve_workspace_path(workspace_path)
            workspace_changed = target_workspace != self._workspace_path
            next_startup_context = dict(startup_context or {})
            next_instruction_policy = dict(instruction_policy or {})
            startup_context_changed = next_startup_context != self._startup_context
            instruction_policy_changed = bool(next_instruction_policy) and (
                next_instruction_policy != self._instruction_policy
            )
            if self._status == OpenCodeStatus.RUNNING and not (
                force_restart
                or workspace_changed
                or startup_context_changed
                or instruction_policy_changed
            ):
                self._startup_context = next_startup_context or dict(self._startup_context)
                if next_instruction_policy:
                    self._instruction_policy = next_instruction_policy
                return True
            if self._status == OpenCodeStatus.STARTING and not (
                force_restart
                or workspace_changed
                or startup_context_changed
                or instruction_policy_changed
            ):
                self._startup_context = next_startup_context or dict(self._startup_context)
                if next_instruction_policy:
                    self._instruction_policy = next_instruction_policy
                if await self.health_check():
                    self._status = OpenCodeStatus.RUNNING
                    if not self._stats.started_at:
                        self._stats.started_at = datetime.now()
                    return True
                logger.warning("OpenCode 处于 STARTING 但健康检查失败，准备强制重启恢复")
                await self._stop_locked()
            if self._status in (OpenCodeStatus.RUNNING, OpenCodeStatus.STARTING) and (
                force_restart or workspace_changed or startup_context_changed or instruction_policy_changed
            ):
                logger.info(
                    "OpenCode 运行中，准备重启: workspace %s -> %s, startup_context_changed=%s, instruction_policy_changed=%s",
                    self._workspace_path,
                    target_workspace,
                    startup_context_changed,
                    instruction_policy_changed,
                )
                await self._stop_locked()

            self._status = OpenCodeStatus.STARTING
            self._stopping = False
            try:
                self._last_start_failure = None
                self._workspace_path = target_workspace
                self._startup_context = next_startup_context
                self._instruction_policy = next_instruction_policy
                binary = Config.get_opencode_binary()
                if not binary or not binary.exists():
                    raise FileNotFoundError("未找到 opencode 可执行文件")

                if platform.system() != "Windows":
                    os.chmod(binary, binary.stat().st_mode | 0o111)
                self._clear_quarantine_if_needed(binary)

                Config.OPENCODE_DATA_DIR.mkdir(parents=True, exist_ok=True)
                Config.OPENCODE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

                baseline_config = await self._build_baseline_config()
                env = os.environ.copy()
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps(baseline_config, ensure_ascii=False)
                env["HOME"] = str(Path.home())
                self._configure_runtime_env(env)
                rules_dir = get_opencode_rules_service().get_current_dir()
                if isinstance(rules_dir, str) and rules_dir.strip():
                    env["OPENCODE_CONFIG_DIR"] = rules_dir.strip()

                stdout_log = open(Config.OPENCODE_LOGS_DIR / "server.out.log", "a", encoding="utf-8")
                stderr_log = open(Config.OPENCODE_LOGS_DIR / "server.err.log", "a", encoding="utf-8")

                cmd = [
                    str(binary),
                    "serve",
                    "--hostname",
                    self.host,
                    "--port",
                    str(self.port),
                    "--cors",
                    "http://localhost:5173",
                    "--cors",
                    "http://127.0.0.1:5173",
                    "--cors",
                    "tauri://localhost",
                    "--cors",
                    "https://tauri.localhost",
                ]
                logger.info("启动 OpenCode: %s", " ".join(cmd))

                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    cwd=str(self._workspace_path),
                    env=env,
                )

                ready = await self._wait_until_ready(timeout=Config.OPENCODE_START_TIMEOUT)
                if not ready:
                    process_returncode = self._process.returncode if self._process else None
                    logger.error("OpenCode 启动后健康检查超时，进程返回码: %s", process_returncode)
                    err_hint = self._read_startup_error_hint()
                    if err_hint:
                        logger.error("OpenCode 启动失败详情(最近 stderr):\n%s", err_hint)
                    self._last_start_failure = {
                        "reason": "health_timeout",
                        "hint": err_hint,
                        "workspace_path": str(target_workspace),
                        "pid": self._process.pid if self._process else None,
                        "process_returncode": process_returncode,
                    }
                    await self._terminate_process()
                    self._status = OpenCodeStatus.ERROR
                    return False

                self._status = OpenCodeStatus.RUNNING
                self._stats.started_at = datetime.now()
                self._stats.health_check_failures = 0
                self._last_start_failure = None
                self._ensure_health_loop()
                logger.info("OpenCode 启动成功: %s", self.base_url)
                return True
            except Exception as e:
                process_returncode = self._process.returncode if self._process else None
                logger.error(
                    "启动 OpenCode 失败: %s (type=%s, returncode=%s)",
                    e,
                    type(e).__name__,
                    process_returncode,
                    exc_info=True,
                )
                err_hint = self._read_startup_error_hint()
                if err_hint:
                    logger.error("OpenCode 启动失败详情(最近 stderr):\n%s", err_hint)
                self._last_start_failure = {
                    "reason": "startup_exception",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "hint": err_hint,
                    "workspace_path": str(target_workspace),
                    "pid": self._process.pid if self._process else None,
                    "process_returncode": process_returncode,
                }
                self._status = OpenCodeStatus.ERROR
                return False

    async def stop(self) -> bool:
        async with self._lock:
            if self._status == OpenCodeStatus.STOPPED:
                return True
            await self._stop_locked()
            return True

    async def restart(self) -> bool:
        if not self._workspace_path:
            logger.error("OpenCode 重启失败：未绑定工作区")
            return False
        await self.stop()
        await asyncio.sleep(0.5)
        return await self.start(
            workspace_path=str(self._workspace_path),
            startup_context=self._startup_context,
            instruction_policy=self._instruction_policy,
        )

    async def health_check(self) -> bool:
        if not self._health_client:
            trust_env = await self._resolve_httpx_trust_env()
            self._health_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=2.0, read=3.0, write=3.0, pool=2.0),
                trust_env=trust_env,
            )
        try:
            resp = await self._health_client.get(f"{self.base_url}/global/health")
            healthy = resp.status_code == 200 and bool(resp.json().get("healthy"))
            self._stats.last_health_check = datetime.now()
            if healthy:
                self._stats.health_check_failures = 0
                if self._status == OpenCodeStatus.UNHEALTHY:
                    self._status = OpenCodeStatus.RUNNING
            else:
                self._stats.health_check_failures += 1
            return healthy
        except Exception:
            self._stats.last_health_check = datetime.now()
            self._stats.health_check_failures += 1
            return False

    async def get_health_payload(self) -> Dict[str, Any]:
        healthy = await self.health_check() if self._status != OpenCodeStatus.STOPPED else False
        return {
            "status": self._status.value,
            "healthy": healthy,
            "base_url": self.base_url,
            "workspace_path": self.workspace_path,
            "pid": self._process.pid if self._process else None,
            "last_start_failure": self.last_start_failure,
            "stats": {
                "started_at": self._stats.started_at.isoformat() if self._stats.started_at else None,
                "last_health_check": self._stats.last_health_check.isoformat() if self._stats.last_health_check else None,
                "health_check_failures": self._stats.health_check_failures,
                "restart_count": self._stats.restart_count,
            },
        }

    async def get_runtime_diagnostics(self) -> Dict[str, Any]:
        health = await self.get_health_payload()
        runtime_log_path = self._resolve_latest_runtime_log_path()
        runtime_tail = self._read_log_tail(runtime_log_path, 220)
        stderr_tail = self._read_log_tail(Config.OPENCODE_LOGS_DIR / "server.err.log", 80)
        analysis = self._analyze_runtime_tail(runtime_tail)
        return {
            "health": health,
            "summary": analysis,
            "runtime_log": str(runtime_log_path) if runtime_log_path else None,
            "runtime_tail": runtime_tail,
            "stderr_tail": stderr_tail,
        }

    async def get_config_providers(self) -> Dict[str, Any]:
        await self._ensure_service_ready()
        return await self._request_json("GET", "/config/providers")

    async def list_agents(self) -> Dict[str, Any]:
        await self._ensure_service_ready()
        return await self._request_json("GET", "/agent")

    async def patch_config(self, patch_data: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_service_ready()
        return await self._request_json("PATCH", "/config", json=patch_data)

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        if not self._http_client:
            trust_env = await self._resolve_httpx_trust_env()
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=25.0, write=10.0, pool=5.0),
                trust_env=trust_env,
            )
        url = f"{self.base_url}{path}"
        max_attempts = 2 if method.upper() == "GET" else 1
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self._http_client.request(method, url, **kwargs)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else {"data": data}
            except httpx.ReadTimeout as err:
                last_error = err
                logger.warning(
                    "OpenCode 请求超时: %s %s (attempt=%s/%s)",
                    method,
                    path,
                    attempt,
                    max_attempts,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(0.35)
                    continue
                raise
            except Exception:
                raise
        if last_error:
            raise last_error
        raise RuntimeError(f"OpenCode 请求失败: {method} {path}")

    @staticmethod
    async def _resolve_httpx_trust_env() -> bool:
        """
        Follow user proxy setting from NetworkSettings:
        - enabled=True  -> allow httpx to read proxy env vars.
        - enabled=False -> ignore env proxy vars entirely.
        """
        try:
            proxy_config = await storage_manager.get_config("system:network:proxy")
            return bool(isinstance(proxy_config, dict) and proxy_config.get("enabled"))
        except Exception:
            # Be conservative on config read failures to avoid unexpected proxy routing.
            return False

    @staticmethod
    def _resolve_workspace_path(workspace_path: Optional[str]) -> Path:
        raw = (workspace_path or "").strip()
        if not raw:
            raise ValueError("OpenCode 启动必须绑定 workspace_path")
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (Config.PROJECT_ROOT / candidate).resolve()
        if not candidate.exists() or not candidate.is_dir():
            raise FileNotFoundError(f"OpenCode 工作区不存在: {candidate}")
        return candidate

    async def _stop_locked(self) -> None:
        self._status = OpenCodeStatus.STOPPING
        self._stopping = True

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        await self._terminate_process()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        if self._health_client:
            await self._health_client.aclose()
            self._health_client = None
        self._status = OpenCodeStatus.STOPPED
        logger.info("OpenCode 已停止")

    async def _wait_until_ready(self, timeout: float) -> bool:
        start = asyncio.get_running_loop().time()
        while (asyncio.get_running_loop().time() - start) < timeout:
            if self._process and self._process.returncode is not None:
                return False
            if await self.health_check():
                return True
            await asyncio.sleep(0.4)
        return False

    async def _ensure_service_ready(self) -> None:
        if self._status not in (OpenCodeStatus.RUNNING, OpenCodeStatus.STARTING):
            raise OpenCodeUnavailableError("OpenCode 未启动，请先调用 start_with_workspace 绑定目录")

        healthy = await self.health_check()
        if not healthy:
            raise OpenCodeUnavailableError("OpenCode 未就绪或健康检查失败")

    @staticmethod
    def _clear_quarantine_if_needed(binary_path: Path) -> None:
        if platform.system() != "Darwin":
            return
        try:
            result = subprocess.run(
                ["xattr", "-d", "com.apple.quarantine", str(binary_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            # 未设置 quarantine 时 xattr 会返回非 0，不应影响启动。
            if result.returncode == 0:
                logger.info("已移除 OpenCode quarantine 属性: %s", binary_path)
            elif "No such xattr" not in (result.stderr or ""):
                logger.warning(
                    "移除 OpenCode quarantine 失败: %s, stderr=%s",
                    binary_path,
                    (result.stderr or "").strip(),
                )
        except Exception as err:
            logger.warning("处理 OpenCode quarantine 属性异常: %r", err)

    @staticmethod
    def _configure_runtime_env(env: Dict[str, str]) -> None:
        # 将 OpenCode 的 XDG 目录固定到 DawnChat 用户数据目录，避免默认 ~/.local/* 不可写导致启动失败。
        runtime_root = Config.OPENCODE_DATA_DIR / "runtime"
        xdg_state_home = runtime_root / "state"
        xdg_data_home = runtime_root / "data"
        xdg_config_home = runtime_root / "config"
        xdg_cache_home = runtime_root / "cache"
        opencode_home = runtime_root / "opencode"
        for folder in (xdg_state_home, xdg_data_home, xdg_config_home, xdg_cache_home, opencode_home):
            folder.mkdir(parents=True, exist_ok=True)

        env["XDG_STATE_HOME"] = str(xdg_state_home)
        env["XDG_DATA_HOME"] = str(xdg_data_home)
        env["XDG_CONFIG_HOME"] = str(xdg_config_home)
        env["XDG_CACHE_HOME"] = str(xdg_cache_home)
        env["OPENCODE_HOME"] = str(opencode_home)
        env["OPENCODE_DISABLE_LSP_DOWNLOAD"] = "true"

    @staticmethod
    def _read_startup_error_hint(max_lines: int = 40) -> str:
        err_log = Config.OPENCODE_LOGS_DIR / "server.err.log"
        if not err_log.exists():
            return ""
        try:
            lines = err_log.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines:
                return ""
            return "\n".join(lines[-max_lines:])
        except Exception:
            return ""

    @staticmethod
    def _resolve_latest_runtime_log_path() -> Optional[Path]:
        log_dir = Config.OPENCODE_DATA_DIR / "runtime" / "data" / "opencode" / "log"
        if not log_dir.exists() or not log_dir.is_dir():
            return None
        candidates = sorted(log_dir.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None

    @staticmethod
    def _read_log_tail(path: Optional[Path], max_lines: int) -> List[str]:
        if not path or not path.exists() or not path.is_file():
            return []
        try:
            rows = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            return rows[-max_lines:] if max_lines > 0 else rows
        except Exception:
            return []

    @staticmethod
    def _analyze_runtime_tail(lines: List[str]) -> Dict[str, Any]:
        if not lines:
            return {"suspected_blocker": "unknown", "reason": "empty_runtime_tail"}

        def last_index(*keywords: str) -> int:
            for index in range(len(lines) - 1, -1, -1):
                row = lines[index]
                if any(keyword in row for keyword in keywords):
                    return index
            return -1

        last_lsp_wait = last_index("waiting for diagnostics")
        last_lsp_result = last_index("got diagnostics", "textDocument/publishDiagnostics")
        last_file_edit = last_index("service=bus type=file.edited publishing")
        last_delta = last_index("service=bus type=message.part.delta publishing")
        last_health = last_index("method=GET path=/global/health request")

        suspected = "unknown"
        reason = "insufficient_signals"
        if last_lsp_wait > last_lsp_result and last_lsp_wait >= last_file_edit:
            suspected = "lsp"
            reason = "diagnostics_wait_without_followup"
        elif last_file_edit > last_delta and last_file_edit >= 0:
            suspected = "tool_or_post_edit"
            reason = "file_edited_without_new_delta"
        elif last_health > last_delta and last_delta >= 0 and (last_health - last_delta) > 30:
            suspected = "transport_or_engine_backpressure"
            reason = "health_only_window_after_delta"

        return {
            "suspected_blocker": suspected,
            "reason": reason,
            "signal_index": {
                "last_lsp_wait": last_lsp_wait,
                "last_lsp_result": last_lsp_result,
                "last_file_edit": last_file_edit,
                "last_delta": last_delta,
                "last_health": last_health,
            },
            "tail_size": len(lines),
        }

    async def _terminate_process(self) -> None:
        if not self._process:
            return
        try:
            if self._process.returncode is not None:
                await self._process.wait()
                return
            self._process.terminate()
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except ProcessLookupError:
            # 进程可能在 terminate 前已自然退出，忽略即可。
            pass
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
        except Exception as e:
            logger.warning("终止 OpenCode 进程时异常: %r", e)
        finally:
            self._process = None

    def _ensure_health_loop(self) -> None:
        if self._health_check_task and not self._health_check_task.done():
            return

        async def _loop() -> None:
            while not self._stopping:
                await asyncio.sleep(Config.OPENCODE_HEALTH_CHECK_INTERVAL)
                healthy = await self.health_check()
                if healthy:
                    continue
                if self._stats.health_check_failures < 3:
                    continue
                self._status = OpenCodeStatus.UNHEALTHY
                if self._stats.restart_count >= Config.OPENCODE_MAX_RESTARTS:
                    logger.error("OpenCode 达到最大重启次数，停止自动重启")
                    continue
                self._stats.restart_count += 1
                logger.warning("OpenCode 健康检查失败，触发自动重启 (第 %s 次)", self._stats.restart_count)
                await self.restart()

        self._health_check_task = asyncio.create_task(_loop())

    async def _build_baseline_config(self) -> Dict[str, Any]:
        result = await self._baseline_config_composer.compose(
            host=self.host,
            port=self.port,
            workspace=self._workspace_path,
            instruction_policy=self._instruction_policy,
            startup_context=self._startup_context,
        )
        logger.info(
            "OpenCode baseline config prepared: workspace=%s providers=%s default_model=%s instructions=%s startup_context=%s mcp_keys=%s",
            self._workspace_path,
            result.configured_providers,
            result.config["model"],
            result.merged_instructions,
            self._startup_context,
            sorted((result.config.get("mcp") or {}).keys()),
        )
        return result.config


_opencode_manager: Optional[OpenCodeManager] = None


def get_opencode_manager() -> OpenCodeManager:
    global _opencode_manager
    if _opencode_manager is None:
        _opencode_manager = OpenCodeManager()
    return _opencode_manager
