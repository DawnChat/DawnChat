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
import shutil
import signal
import socket
import subprocess
from typing import Any, Dict, List, Optional

import httpx

from app.config import Config
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.services.network_service import NetworkService
from app.services.opencode_baseline_config_composer import OpenCodeBaselineConfigComposer
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


@dataclass
class OpenCodeReadyResult:
    ready: bool
    reason: str = ""
    listener_pid: Optional[int] = None


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
        self._runtime_port: Optional[int] = None
        self._server_out_open_mode = "w"
        self._server_err_open_mode = "w"

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
        return int(self._runtime_port or Config.OPENCODE_PORT)

    @property
    def base_url(self) -> str:
        if self._runtime_port is None:
            return ""
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
            logger.info(
                "OpenCode start request: status=%s current_workspace=%s target_workspace=%s force_restart=%s workspace_changed=%s startup_context_changed=%s instruction_policy_changed=%s startup_context=%s",
                self._status.value,
                self._workspace_path,
                target_workspace,
                force_restart,
                workspace_changed,
                startup_context_changed,
                instruction_policy_changed,
                next_startup_context,
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
                logger.info(
                    "OpenCode start reused existing process: workspace=%s pid=%s startup_context=%s",
                    self._workspace_path,
                    self._process.pid if self._process else None,
                    self._startup_context,
                )
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
                    logger.info(
                        "OpenCode start joined in-flight process: workspace=%s pid=%s startup_context=%s",
                        self._workspace_path,
                        self._process.pid if self._process else None,
                        self._startup_context,
                    )
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
                self._runtime_port = self._allocate_runtime_port()
                binary = Config.get_opencode_binary()
                if not binary or not binary.exists():
                    raise FileNotFoundError("未找到 opencode 可执行文件")

                if platform.system() != "Windows":
                    os.chmod(binary, binary.stat().st_mode | 0o111)
                self._clear_quarantine_if_needed(binary)

                Config.OPENCODE_DATA_DIR.mkdir(parents=True, exist_ok=True)
                Config.OPENCODE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

                await self._ensure_opencode_models_dev_file()

                baseline_config = await self._build_baseline_config()
                env = os.environ.copy()
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps(baseline_config, ensure_ascii=False)
                env["HOME"] = str(Path.home())
                self._configure_runtime_env(env)
                # OpenCode 会按 cache/version 清空 $XDG_CACHE_HOME/opencode，写在 cache 里的 models.json 会被删掉；
                # 使用用户数据目录 + OPENCODE_MODELS_PATH，并关闭 models.dev 定时拉取（见上游 packages/opencode/src/provider/models.ts）。
                models_dev_file = Config.OPENCODE_DATA_DIR / "opencode_models_dev_api.json"
                env["OPENCODE_MODELS_PATH"] = str(models_dev_file.resolve())
                env["OPENCODE_DISABLE_MODELS_FETCH"] = "true"
                rules_dir = get_opencode_rules_service().get_current_dir()
                if isinstance(rules_dir, str) and rules_dir.strip():
                    env["OPENCODE_CONFIG_DIR"] = rules_dir.strip()

                models_path_resolved = Path(env["OPENCODE_MODELS_PATH"])
                try:
                    models_exists = models_path_resolved.is_file()
                    models_size = models_path_resolved.stat().st_size if models_exists else 0
                except OSError:
                    models_exists = False
                    models_size = -1
                logger.info(
                    "OpenCode spawn env（models.dev）: OPENCODE_MODELS_PATH=%s exists=%s size_bytes=%s "
                    "OPENCODE_DISABLE_MODELS_FETCH=%s OPENCODE_HOME=%s XDG_STATE_HOME=%s；子进程 stderr 见 %s；"
                    "可与该条时间戳对照 server.err.log 判断是否为新包",
                    models_path_resolved,
                    models_exists,
                    models_size,
                    env.get("OPENCODE_DISABLE_MODELS_FETCH"),
                    env.get("OPENCODE_HOME"),
                    env.get("XDG_STATE_HOME"),
                    Config.OPENCODE_LOGS_DIR / "server.err.log",
                )

                self._rotate_opencode_session_server_logs()
                stdout_log = open(
                    Config.OPENCODE_LOGS_DIR / "server.out.log",
                    self._server_out_open_mode,
                    encoding="utf-8",
                )
                stderr_log = open(
                    Config.OPENCODE_LOGS_DIR / "server.err.log",
                    self._server_err_open_mode,
                    encoding="utf-8",
                )

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
                logger.info(
                    "启动 OpenCode: cmd=%s cwd=%s port=%s startup_context=%s",
                    " ".join(cmd),
                    self._workspace_path,
                    self.port,
                    self._startup_context,
                )

                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    cwd=str(self._workspace_path),
                    env=env,
                )

                ready = await self._wait_until_ready(timeout=Config.OPENCODE_START_TIMEOUT)
                if not ready.ready:
                    process_returncode = self._process.returncode if self._process else None
                    rc_diag = self._format_process_returncode(process_returncode)
                    logger.error(
                        "OpenCode 启动失败: reason=%s process_returncode=%s listener_pid=%s port=%s %s",
                        ready.reason or "health_timeout",
                        process_returncode,
                        ready.listener_pid,
                        self.port,
                        rc_diag,
                    )
                    err_hint = self._read_startup_error_hint()
                    if err_hint:
                        logger.error("OpenCode 启动失败详情(最近 stderr):\n%s", err_hint)
                    runtime_log = self._resolve_latest_runtime_log_path()
                    if runtime_log:
                        if (ready.reason == "process_exited") or (not err_hint.strip()):
                            logger.error(
                                "OpenCode 启动失败(次级线索): runtime 日志目录内最新文件 mtime=%s path=%s",
                                datetime.fromtimestamp(runtime_log.stat().st_mtime).isoformat(),
                                runtime_log,
                            )
                        else:
                            logger.info(
                                "OpenCode 启动失败(参考): runtime 日志 path=%s",
                                runtime_log,
                            )
                    self._last_start_failure = {
                        "reason": ready.reason or "health_timeout",
                        "hint": err_hint,
                        "returncode_diagnosis": rc_diag,
                        "runtime_log_hint": str(runtime_log) if runtime_log else "",
                        "workspace_path": str(target_workspace),
                        "port": self.port,
                        "pid": self._process.pid if self._process else None,
                        "listener_pid": ready.listener_pid,
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
                logger.info(
                    "OpenCode 启动成功: base_url=%s pid=%s port=%s",
                    self.base_url,
                    self._process.pid if self._process else None,
                    self.port,
                )
                return True
            except Exception as e:
                process_returncode = self._process.returncode if self._process else None
                rc_diag = self._format_process_returncode(process_returncode)
                logger.error(
                    "启动 OpenCode 失败: %s (type=%s, returncode=%s %s)",
                    e,
                    type(e).__name__,
                    process_returncode,
                    rc_diag,
                    exc_info=True,
                )
                err_hint = self._read_startup_error_hint()
                if err_hint:
                    logger.error("OpenCode 启动失败详情(最近 stderr):\n%s", err_hint)
                runtime_log = self._resolve_latest_runtime_log_path()
                if runtime_log:
                    logger.info("OpenCode 启动异常(参考): runtime 日志 path=%s", runtime_log)
                self._last_start_failure = {
                    "reason": "startup_exception",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "hint": err_hint,
                    "returncode_diagnosis": rc_diag,
                    "runtime_log_hint": str(runtime_log) if runtime_log else "",
                    "workspace_path": str(target_workspace),
                    "port": self.port,
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
        if not self.base_url:
            self._stats.last_health_check = datetime.now()
            self._stats.health_check_failures += 1
            return False
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
        except Exception as err:
            self._stats.last_health_check = datetime.now()
            self._stats.health_check_failures += 1
            logger.debug(
                "OpenCode health check failed: %s: %s",
                type(err).__name__,
                err,
                exc_info=True,
            )
            if self._stats.health_check_failures == 1:
                logger.warning(
                    "OpenCode health check failed (%s: %s); 后续失败仅记 DEBUG，可调高日志级别排障",
                    type(err).__name__,
                    err,
                )
            return False

    async def get_health_payload(self) -> Dict[str, Any]:
        healthy = await self.health_check() if self._status != OpenCodeStatus.STOPPED else False
        return {
            "status": self._status.value,
            "healthy": healthy,
            "base_url": self.base_url,
            "port": self._runtime_port,
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
        """Delegate to NetworkService (same rule as image-search Edge client)."""
        return await NetworkService.user_proxy_httpx_trust_env()

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
        self._runtime_port = None
        self._status = OpenCodeStatus.STOPPED
        logger.info("OpenCode 已停止")

    async def _wait_until_ready(self, timeout: float) -> OpenCodeReadyResult:
        start = asyncio.get_running_loop().time()
        while (asyncio.get_running_loop().time() - start) < timeout:
            if self._process and self._process.returncode is not None:
                return OpenCodeReadyResult(ready=False, reason="process_exited")
            if await self.health_check():
                expected_pid = self._process.pid if self._process else None
                listener_pid = await asyncio.to_thread(self._resolve_listener_pid, self.port)
                if expected_pid and listener_pid and listener_pid != expected_pid:
                    logger.error(
                        "OpenCode listener ownership mismatch: expected_pid=%s listener_pid=%s port=%s base_url=%s",
                        expected_pid,
                        listener_pid,
                        self.port,
                        self.base_url,
                    )
                    return OpenCodeReadyResult(
                        ready=False,
                        reason="listener_pid_mismatch",
                        listener_pid=listener_pid,
                    )
                if expected_pid and listener_pid is None:
                    logger.warning(
                        "OpenCode listener PID verification skipped: expected_pid=%s port=%s",
                        expected_pid,
                        self.port,
                    )
                return OpenCodeReadyResult(ready=True, listener_pid=listener_pid)
            await asyncio.sleep(0.4)
        return OpenCodeReadyResult(ready=False, reason="health_timeout")

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
        run_mode = str(os.getenv("DAWNCHAT_RUN_MODE", "")).strip().lower()
        if Config.IS_PBS_APP and run_mode == "release":
            logger.info("正式 release 环境，跳过 OpenCode quarantine 清理: %s", binary_path)
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

    async def _ensure_opencode_models_dev_file(self) -> None:
        """写入 OpenCode 读取的 models.dev 快照路径（OPENCODE_MODELS_PATH），避免走外网与 cache 被清空。

        上游实现：packages/opencode/src/provider/models.ts（Data 优先读 OPENCODE_MODELS_PATH）、
        packages/opencode/src/global/index.ts（CACHE_VERSION 不匹配时会清空整个 Global.Path.cache）。

        此前把 models.json 放在 XDG_CACHE_HOME/opencode 下会被启动时清空，预取无效；改存 DATA_DIR 并配合
        OPENCODE_DISABLE_MODELS_FETCH，可关闭模块加载时的 ModelsDev.refresh() 定时拉取（同文件 models.ts）。
        """
        dest = Config.OPENCODE_DATA_DIR / "opencode_models_dev_api.json"
        min_bytes = 64

        try:
            if dest.exists() and dest.stat().st_size >= min_bytes:
                return
        except OSError:
            pass

        try:
            home_models = Path.home() / ".cache" / "opencode" / "models.json"
            if home_models.is_file() and home_models.stat().st_size >= min_bytes:
                shutil.copy2(home_models, dest)
                logger.info("OpenCode models.dev 快照：已从 CLI 缓存复用 %s -> %s", home_models, dest)
                return
        except OSError as err:
            logger.debug("复用 OpenCode CLI models.json 失败: %s", err)

        trust_env = await self._resolve_httpx_trust_env()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(25.0, connect=8.0),
                trust_env=trust_env,
                follow_redirects=True,
            ) as client:
                response = await client.get("https://models.dev/api.json")
                response.raise_for_status()
                body = response.content
                if len(body) < min_bytes:
                    raise ValueError("models.dev 响应过短")
                dest.write_bytes(body)
                logger.info(
                    "OpenCode models.dev 快照：已下载 api.json -> %s (%s bytes)",
                    dest,
                    len(body),
                )
                return
        except Exception as err:
            logger.warning("无法下载 models.dev 快照，将写入空对象占位（依赖 DawnChat 注入的 provider 配置）: %s", err)

        try:
            dest.write_text("{}", encoding="utf-8")
            logger.info("OpenCode models.dev 快照：已写入空 JSON 占位 %s", dest)
        except OSError as err:
            logger.error("无法写入 OpenCode models 占位文件 %s: %s", dest, err)

    _ROTATED_SERVER_LOG_KEEP = 20

    def _rotate_opencode_session_server_logs(self) -> None:
        """将累积的 server.out/err 轮转为带时间戳备份，再以 'w' 打开当次会话（失败则对该文件退化为 'a'）。"""
        logs_dir = Config.OPENCODE_LOGS_DIR
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            logger.warning("OpenCode 日志目录不可用，跳过轮转: %s err=%s", logs_dir, err)
            self._server_out_open_mode = "w"
            self._server_err_open_mode = "w"
            return

        out_mode = OpenCodeManager._try_rotate_session_server_log(logs_dir, "server.out.log")
        err_mode = OpenCodeManager._try_rotate_session_server_log(logs_dir, "server.err.log")
        self._server_out_open_mode = out_mode
        self._server_err_open_mode = err_mode

    @staticmethod
    def _try_rotate_session_server_log(logs_dir: Path, filename: str) -> str:
        """若日志文件不存在则返回 'w'；若存在且轮转成功返回 'w'；轮转失败返回 'a' 以免截断丢失未备份内容。"""
        path = logs_dir / filename
        try:
            exists = path.exists()
        except OSError:
            return "a"
        if not exists:
            return "w"
        try:
            if not path.is_file():
                return "a"
        except OSError:
            return "a"
        stem = path.stem
        ts = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        backup = logs_dir / f"{stem}.{ts}.log"
        try:
            path.rename(backup)
        except OSError as err:
            logger.warning(
                "OpenCode 日志轮转失败，本会话对该文件使用追加写: path=%s err=%s",
                path,
                err,
            )
            return "a"
        try:
            OpenCodeManager._prune_rotated_server_log_backups(
                logs_dir,
                stem,
                keep=OpenCodeManager._ROTATED_SERVER_LOG_KEEP,
            )
        except Exception as err:
            logger.debug("OpenCode 日志轮转清理跳过: %s", err)
        return "w"

    @staticmethod
    def _prune_rotated_server_log_backups(logs_dir: Path, stem: str, keep: int) -> None:
        """删除过旧的轮转备份，仅保留 stem 前缀下最近 keep 个（按 mtime）。"""
        primary = f"{stem}.log"
        candidates: List[Path] = []
        try:
            for p in logs_dir.iterdir():
                if not p.is_file():
                    continue
                if p.name == primary:
                    continue
                if not (p.name.startswith(f"{stem}.") and p.name.endswith(".log")):
                    continue
                candidates.append(p)
        except OSError:
            return
        if len(candidates) <= keep:
            return
        candidates.sort(key=lambda item: item.stat().st_mtime)
        for victim in candidates[: max(0, len(candidates) - keep)]:
            try:
                victim.unlink()
            except OSError:
                pass

    @staticmethod
    def _format_process_returncode(rc: Optional[int]) -> str:
        if rc is None:
            return "returncode_diagnosis=n/a"
        if rc < 0:
            sig = -rc
            label = ""
            try:
                label = signal.strsignal(sig) or ""
            except (ValueError, OSError):
                label = ""
            if label:
                return f"returncode_diagnosis=signal {sig} ({label})"
            return f"returncode_diagnosis=signal {sig}"
        return f"returncode_diagnosis=exit_status {rc}"

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
            "OpenCode baseline config prepared: workspace=%s port=%s providers=%s default_model=%s instructions=%s startup_context=%s mcp_keys=%s",
            self._workspace_path,
            self.port,
            result.configured_providers,
            result.config["model"],
            result.merged_instructions,
            self._startup_context,
            sorted((result.config.get("mcp") or {}).keys()),
        )
        return result.config

    def _allocate_runtime_port(self) -> int:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.host, 0))
                return int(sock.getsockname()[1])
        except OSError as err:
            logger.warning(
                "OpenCode 动态端口分配失败，回退到配置端口: host=%s port=%s err=%s",
                self.host,
                Config.OPENCODE_PORT,
                err,
            )
            return int(Config.OPENCODE_PORT)

    @staticmethod
    def _resolve_listener_pid(port: int) -> Optional[int]:
        try:
            result = subprocess.run(
                ["lsof", "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-t"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return None
        except Exception as err:
            logger.warning("读取 OpenCode 监听 PID 失败: port=%s err=%r", port, err)
            return None

        if result.returncode not in (0, 1):
            logger.warning(
                "读取 OpenCode 监听 PID 命令失败: port=%s returncode=%s stderr=%s",
                port,
                result.returncode,
                (result.stderr or "").strip(),
            )
            return None

        for line in (result.stdout or "").splitlines():
            text = str(line or "").strip()
            if text.isdigit():
                return int(text)
        return None


_opencode_manager: Optional[OpenCodeManager] = None


def get_opencode_manager() -> OpenCodeManager:
    global _opencode_manager
    if _opencode_manager is None:
        _opencode_manager = OpenCodeManager()
    return _opencode_manager
