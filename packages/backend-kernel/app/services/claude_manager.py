from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import shlex
import shutil
from typing import Any, Dict, Optional

import httpx

from app.config import Config
from app.services.agent_catalog_service import get_agent_catalog_service
from app.services.claude_baseline_config_composer import ClaudeBaselineConfigComposer
from app.services.model_list_service import SUPPORTED_PROVIDERS
from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("claude_manager")


class ClaudeUnavailableError(RuntimeError):
    pass


class ClaudeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    UNHEALTHY = "unhealthy"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ClaudeStats:
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    health_check_failures: int = 0
    restart_count: int = 0


class ClaudeManager:
    def __init__(self) -> None:
        self._process: Optional[asyncio.subprocess.Process] = None
        self._status = ClaudeStatus.STOPPED
        self._stats = ClaudeStats()
        self._health_client: Optional[httpx.AsyncClient] = None
        self._health_check_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()
        self._stopping = False
        self._workspace_path: Optional[Path] = None
        self._startup_context: Dict[str, Any] = {}
        self._instruction_policy: Dict[str, Any] = {}
        self._runtime_config: Dict[str, Any] = {}
        self._runtime_config_path: Optional[Path] = None
        self._composer = ClaudeBaselineConfigComposer()

    @property
    def status(self) -> ClaudeStatus:
        return self._status

    @property
    def stats(self) -> ClaudeStats:
        return self._stats

    @property
    def host(self) -> str:
        return Config.CLAUDE_HOST

    @property
    def port(self) -> int:
        return Config.CLAUDE_PORT

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def workspace_path(self) -> Optional[str]:
        return str(self._workspace_path) if self._workspace_path else None

    @property
    def startup_context(self) -> Dict[str, Any]:
        return dict(self._startup_context)

    async def start(
        self,
        *,
        workspace_path: str,
        force_restart: bool = False,
        startup_context: Optional[Dict[str, Any]] = None,
        instruction_policy: Optional[Dict[str, Any]] = None,
        rules_dir: Optional[str] = None,
    ) -> bool:
        async with self._lock:
            target_workspace = self._resolve_workspace_path(workspace_path)
            workspace_changed = target_workspace != self._workspace_path
            next_startup_context = dict(startup_context or {})
            next_instruction_policy = dict(instruction_policy or {})
            if self._status in (ClaudeStatus.RUNNING, ClaudeStatus.STARTING) and not (
                force_restart or workspace_changed
            ):
                self._startup_context = next_startup_context or dict(self._startup_context)
                if next_instruction_policy:
                    self._instruction_policy = next_instruction_policy
                return True
            if self._status in (ClaudeStatus.RUNNING, ClaudeStatus.STARTING) and (
                force_restart or workspace_changed
            ):
                await self._stop_locked()

            self._status = ClaudeStatus.STARTING
            self._stopping = False
            try:
                self._workspace_path = target_workspace
                self._startup_context = next_startup_context
                self._instruction_policy = next_instruction_policy
                command = self._resolve_claude_command()
                if not command:
                    raise ClaudeUnavailableError("本机未检测到 claude 命令，Claude Code 不可用")

                Config.CLAUDE_DATA_DIR.mkdir(parents=True, exist_ok=True)
                Config.CLAUDE_LOGS_DIR.mkdir(parents=True, exist_ok=True)

                compose_result = await self._composer.compose(
                    workspace=self._workspace_path,
                    instruction_policy=self._instruction_policy,
                    startup_context=self._startup_context,
                    rules_dir=rules_dir,
                )
                self._runtime_config = compose_result.config
                self._runtime_config_path = await self._write_runtime_config_file(compose_result.config)

                env = os.environ.copy()
                env["HOME"] = str(Path.home())
                env["DAWNCHAT_CLAUDE_RUNTIME_CONFIG"] = str(self._runtime_config_path)
                normalized_rules_dir = str(rules_dir or "").strip()
                if normalized_rules_dir:
                    env["CLAUDE_CONFIG_DIR"] = normalized_rules_dir

                stdout_log = open(Config.CLAUDE_LOGS_DIR / "server.out.log", "a", encoding="utf-8")
                stderr_log = open(Config.CLAUDE_LOGS_DIR / "server.err.log", "a", encoding="utf-8")

                cmd = self._build_start_command(command)
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    cwd=str(self._workspace_path),
                    env=env,
                )

                ready = await self._wait_until_ready(timeout=Config.CLAUDE_START_TIMEOUT)
                if not ready:
                    await self._terminate_process()
                    self._status = ClaudeStatus.ERROR
                    return False
                self._status = ClaudeStatus.RUNNING
                self._stats.started_at = datetime.now()
                self._stats.health_check_failures = 0
                self._ensure_health_loop()
                return True
            except ClaudeUnavailableError:
                self._status = ClaudeStatus.ERROR
                raise
            except Exception:
                self._status = ClaudeStatus.ERROR
                logger.exception("启动 Claude 失败")
                return False

    async def stop(self) -> bool:
        async with self._lock:
            if self._status == ClaudeStatus.STOPPED:
                return True
            await self._stop_locked()
            return True

    async def restart(self) -> bool:
        if not self._workspace_path:
            return False
        await self.stop()
        await asyncio.sleep(0.3)
        return await self.start(
            workspace_path=str(self._workspace_path),
            startup_context=self._startup_context,
            instruction_policy=self._instruction_policy,
            rules_dir=self._runtime_config.get("rules_dir"),
        )

    async def health_check(self) -> bool:
        healthy = self._process is not None and self._process.returncode is None
        if healthy and Config.CLAUDE_HEALTH_ENDPOINT:
            if not self._health_client:
                self._health_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(connect=2.0, read=3.0, write=3.0, pool=2.0),
                    trust_env=True,
                )
            endpoint = str(Config.CLAUDE_HEALTH_ENDPOINT).strip()
            if endpoint:
                url = f"{self.base_url}{endpoint if endpoint.startswith('/') else '/' + endpoint}"
                try:
                    resp = await self._health_client.get(url)
                    if Config.CLAUDE_HEALTH_STRICT:
                        healthy = healthy and resp.status_code == 200
                except Exception:
                    if Config.CLAUDE_HEALTH_STRICT:
                        healthy = False
        self._stats.last_health_check = datetime.now()
        if healthy:
            self._stats.health_check_failures = 0
            if self._status == ClaudeStatus.UNHEALTHY:
                self._status = ClaudeStatus.RUNNING
        else:
            self._stats.health_check_failures += 1
        return healthy

    async def get_health_payload(self) -> Dict[str, Any]:
        healthy = await self.health_check()
        command = self._resolve_claude_command()
        state = self._status.value
        if not command and self._process is None:
            state = "unavailable"
        return {
            "state": state,
            "healthy": healthy,
            "cli_available": bool(command),
            "cli_command": command,
            "workspace_path": self.workspace_path,
            "base_url": self.base_url,
            "runtime_config_path": str(self._runtime_config_path) if self._runtime_config_path else None,
            "stats": {
                "started_at": self._stats.started_at.isoformat() if self._stats.started_at else None,
                "last_health_check": (
                    self._stats.last_health_check.isoformat() if self._stats.last_health_check else None
                ),
                "health_check_failures": self._stats.health_check_failures,
                "restart_count": self._stats.restart_count,
            },
        }

    async def get_runtime_diagnostics(self) -> Dict[str, Any]:
        payload = await self.get_health_payload()
        payload["process"] = {
            "pid": self._process.pid if self._process else None,
            "returncode": self._process.returncode if self._process else None,
        }
        payload["runtime_config"] = dict(self._runtime_config)
        return payload

    async def get_config_providers(self) -> Dict[str, Any]:
        providers: list[Dict[str, Any]] = []
        for provider_id, provider in SUPPORTED_PROVIDERS.items():
            aliases = ("google",) if provider_id == "gemini" else tuple()
            configured = False
            for candidate in (provider_id, *aliases):
                api_key = await storage_manager.get_api_key(candidate)
                if isinstance(api_key, str) and api_key.strip():
                    configured = True
                    break
            providers.append(
                {
                    "id": provider_id,
                    "name": str(provider.get("name") or provider_id),
                    "configured": configured,
                    "available": configured,
                    "models": list(provider.get("models") or []),
                }
            )
        return {"providers": providers}

    async def patch_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        if not self._runtime_config:
            raise ClaudeUnavailableError("Claude 未就绪，无法更新配置")
        updates = dict(patch or {})
        if "model" in updates:
            self._runtime_config["model"] = updates["model"]
        if "default_agent" in updates:
            self._runtime_config["default_agent"] = updates["default_agent"]
        if "provider" in updates and isinstance(updates["provider"], dict):
            providers = self._runtime_config.setdefault("providers", {})
            providers.update(updates["provider"])
        if self._runtime_config_path:
            await self._write_runtime_config_file(self._runtime_config, force_path=self._runtime_config_path)
        return {"updated": True, "config": dict(self._runtime_config)}

    async def list_agents(self) -> Dict[str, Any]:
        workspace = str(self._workspace_path) if self._workspace_path else None
        rows = get_agent_catalog_service().list_agents(workspace)
        return {"agents": rows}

    async def _write_runtime_config_file(
        self,
        payload: Dict[str, Any],
        *,
        force_path: Optional[Path] = None,
    ) -> Path:
        target = force_path
        if target is None:
            target = Config.CLAUDE_DATA_DIR / "runtime-config.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _resolve_workspace_path(self, workspace_path: str) -> Path:
        resolved = Path(str(workspace_path or "")).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(f"workspace 不存在: {resolved}")
        return resolved

    def _resolve_claude_command(self) -> Optional[str]:
        resolved = shutil.which("claude")
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
        return None

    def _build_start_command(self, command: str) -> list[str]:
        raw = str(Config.CLAUDE_START_ARGS or "").strip()
        if raw:
            return [command, *shlex.split(raw)]
        return [command, "serve", "--host", self.host, "--port", str(self.port)]

    async def _wait_until_ready(self, timeout: float) -> bool:
        timeout_at = asyncio.get_running_loop().time() + max(timeout, 0.1)
        while asyncio.get_running_loop().time() < timeout_at:
            if self._process and self._process.returncode is not None:
                return False
            healthy = await self.health_check()
            if healthy:
                return True
            await asyncio.sleep(0.3)
        return False

    def _ensure_health_loop(self) -> None:
        if self._health_check_task and not self._health_check_task.done():
            return
        self._health_check_task = asyncio.create_task(self._health_loop())

    async def _health_loop(self) -> None:
        while not self._stopping and self._status in {
            ClaudeStatus.STARTING,
            ClaudeStatus.RUNNING,
            ClaudeStatus.UNHEALTHY,
        }:
            healthy = await self.health_check()
            if not healthy:
                self._status = ClaudeStatus.UNHEALTHY
                if self._stats.health_check_failures >= max(1, Config.CLAUDE_MAX_RESTARTS):
                    break
            await asyncio.sleep(max(0.2, Config.CLAUDE_HEALTH_CHECK_INTERVAL))

    async def _stop_locked(self) -> None:
        self._status = ClaudeStatus.STOPPING
        self._stopping = True
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        await self._terminate_process()
        if self._health_client:
            await self._health_client.aclose()
            self._health_client = None
        self._status = ClaudeStatus.STOPPED
        self._stopping = False

    async def _terminate_process(self) -> None:
        if not self._process:
            return
        process = self._process
        self._process = None
        try:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        except ProcessLookupError:
            return


_claude_manager: Optional[ClaudeManager] = None


def get_claude_manager() -> ClaudeManager:
    global _claude_manager
    if _claude_manager is None:
        _claude_manager = ClaudeManager()
    return _claude_manager
