from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from typing import Any, Optional

from app.config import Config
from app.services.opencode_manager import get_opencode_manager
from app.utils.logger import get_logger

logger = get_logger("iwp_mcp_service")


class IwpMcpService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @staticmethod
    def tool_definitions() -> list[dict[str, Any]]:
        base_schema = {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "CLI args after command name",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory. Relative paths are resolved from OpenCode workspace.",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1800,
                    "description": "Command timeout in seconds.",
                },
            },
        }
        return [
            {
                "name": "iwp_build",
                "description": "Run iwp-build CLI with raw stdout/stderr passthrough.",
                "inputSchema": base_schema,
            },
            {
                "name": "iwp_lint",
                "description": "Run iwp-lint CLI with raw stdout/stderr passthrough.",
                "inputSchema": base_schema,
            },
        ]

    def _resolve_cwd(self, raw_cwd: str) -> Path:
        workspace = Path(get_opencode_manager().workspace_path or Config.PROJECT_ROOT).expanduser().resolve()
        value = str(raw_cwd or "").strip()
        if not value:
            return workspace
        candidate = Path(value)
        resolved = candidate.expanduser().resolve() if candidate.is_absolute() else (workspace / candidate).resolve()
        try:
            resolved.relative_to(workspace)
        except ValueError as err:
            raise RuntimeError("cwd must be inside current workspace") from err
        return resolved

    @staticmethod
    def _resolve_python() -> Path:
        python_path = Config.get_pbs_python()
        if python_path is None or not python_path.exists():
            fallback = Path(sys.executable).expanduser().resolve()
            if fallback.exists():
                return fallback
            raise RuntimeError(
                "Python runtime is not available. Install/configure PBS python, or ensure system python can run iwp_build/iwp_lint modules."
            )
        return python_path

    @staticmethod
    async def _python_has_module(python_path: Path, module_name: str) -> bool:
        probe = await asyncio.create_subprocess_exec(
            str(python_path),
            "-c",
            "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)",
            module_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await probe.wait()
        return probe.returncode == 0

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized_tool = str(tool_name or "").strip()
        if normalized_tool not in {"iwp_build", "iwp_lint"}:
            return {
                "ok": False,
                "error": f"Unsupported iwp tool: {normalized_tool}. Allowed: iwp_build, iwp_lint",
            }
        module_name = "iwp_build.cli" if normalized_tool == "iwp_build" else "iwp_lint.cli"
        package_name = "iwp_build" if normalized_tool == "iwp_build" else "iwp_lint"
        raw_args = arguments.get("args")
        args = [str(item) for item in raw_args] if isinstance(raw_args, list) else []
        try:
            timeout_seconds = int(arguments.get("timeout_seconds") or 600)
        except (TypeError, ValueError):
            return {"ok": False, "error": "timeout_seconds must be an integer"}
        timeout_seconds = max(1, min(timeout_seconds, 1800))
        try:
            cwd = self._resolve_cwd(str(arguments.get("cwd") or ""))
        except RuntimeError as err:
            return {"ok": False, "error": str(err)}
        try:
            python_path = self._resolve_python()
        except RuntimeError as err:
            return {"ok": False, "error": str(err)}
        if not await self._python_has_module(python_path, package_name):
            return {
                "ok": False,
                "error": (
                    f"Module `{package_name}` is not available in python `{python_path}`. "
                    "Install iwp tools first, for example: `python -m pip install iwp-build iwp-lint`."
                ),
            }
        command = [str(python_path), "-m", module_name, *args]

        async with self._lock:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timed_out = False
            try:
                stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                timed_out = True
                process.kill()
                await process.wait()
                stdout_data = b""
                stderr_data = b""

        stdout_text = stdout_data.decode("utf-8", errors="replace")
        stderr_text = stderr_data.decode("utf-8", errors="replace")
        result = {
            "tool": normalized_tool,
            "command": command,
            "cwd": str(cwd),
            "exit_code": int(process.returncode or 0),
            "stdout": stdout_text,
            "stderr": stderr_text,
            "timed_out": timed_out,
        }
        if timed_out:
            logger.warning("iwp_mcp command timeout tool=%s cwd=%s timeout=%s", normalized_tool, cwd, timeout_seconds)
            return {"ok": False, "error": "command timeout", "result": result}
        if process.returncode == 0:
            return {"ok": True, "result": result}
        return {"ok": False, "error": f"command exited with code {process.returncode}", "result": result}


_iwp_mcp_service: Optional[IwpMcpService] = None


def get_iwp_mcp_service() -> IwpMcpService:
    global _iwp_mcp_service
    if _iwp_mcp_service is None:
        _iwp_mcp_service = IwpMcpService()
    return _iwp_mcp_service
