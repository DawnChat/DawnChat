from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable
import uuid

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("plugin_iwp_workspace_application_service")


class PluginIwpWorkspaceApplicationService:
    def __init__(self, *, get_plugin_path: Callable[[str], str | None]) -> None:
        self._get_plugin_path = get_plugin_path
        self._task_lock = asyncio.Lock()
        self._build_tasks: dict[str, dict[str, Any]] = {}

    def list_markdown_files(self, plugin_id: str) -> dict[str, Any]:
        iwp_root = self._resolve_iwp_root(plugin_id)
        files: list[dict[str, Any]] = []
        for file_path in sorted(iwp_root.rglob("*.md"), key=lambda item: item.as_posix()):
            if any(part.startswith(".") for part in file_path.relative_to(iwp_root).parts):
                continue
            relative = file_path.relative_to(iwp_root).as_posix()
            stat = file_path.stat()
            files.append(
                {
                    "path": relative,
                    "name": file_path.name,
                    "size": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return {
            "iwp_root": iwp_root.name,
            "files": files,
        }

    def has_iwp_requirements(self, plugin_id: str) -> bool:
        try:
            self._resolve_iwp_root(plugin_id)
            return True
        except RuntimeError:
            return False

    def read_markdown_file(self, plugin_id: str, relative_path: str) -> dict[str, Any]:
        iwp_root = self._resolve_iwp_root(plugin_id)
        target = self._resolve_markdown_path(iwp_root, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Markdown file not found: {relative_path}")
        content = target.read_text(encoding="utf-8")
        return {
            "path": target.relative_to(iwp_root).as_posix(),
            "content": content,
            "content_hash": self._sha256(content),
            "updated_at": datetime.fromtimestamp(target.stat().st_mtime).isoformat(),
        }

    def save_markdown_file(
        self,
        plugin_id: str,
        relative_path: str,
        content: str,
        expected_hash: str = "",
    ) -> dict[str, Any]:
        iwp_root = self._resolve_iwp_root(plugin_id)
        target = self._resolve_markdown_path(iwp_root, relative_path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Markdown file not found: {relative_path}")
        current_content = target.read_text(encoding="utf-8")
        current_hash = self._sha256(current_content)
        normalized_expected = str(expected_hash or "").strip()
        if normalized_expected and normalized_expected != current_hash:
            raise RuntimeError("Markdown file has been modified externally. Please reload before saving.")
        target.write_text(content, encoding="utf-8")
        return {
            "path": target.relative_to(iwp_root).as_posix(),
            "content_hash": self._sha256(content),
            "updated_at": datetime.fromtimestamp(target.stat().st_mtime).isoformat(),
        }

    async def start_build(self, plugin_id: str) -> str:
        plugin_root = self._resolve_plugin_root(plugin_id)
        iwp_config = plugin_root / ".iwp-lint.yaml"
        if not iwp_config.exists():
            raise RuntimeError("Missing .iwp-lint.yaml in plugin root")
        task_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()
        payload = {
            "task_id": task_id,
            "plugin_id": plugin_id,
            "status": "queued",
            "stage": "queued",
            "message": "IWP build queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        async with self._task_lock:
            self._build_tasks[task_id] = payload
        asyncio.create_task(self._run_build_task(task_id=task_id, plugin_id=plugin_id, plugin_root=plugin_root))
        return task_id

    async def get_build_task(self, task_id: str) -> dict[str, Any] | None:
        async with self._task_lock:
            task = self._build_tasks.get(task_id)
            if task is None:
                return None
            return dict(task)

    async def _run_build_task(self, *, task_id: str, plugin_id: str, plugin_root: Path) -> None:
        started_at = datetime.now().isoformat()
        await self._update_task(
            task_id,
            status="running",
            stage="session_bootstrap",
            message="Bootstrapping IWP session",
            started_at=started_at,
        )
        try:
            python_path = self._resolve_python()
            if not await self._python_has_module(python_path, "iwp_build"):
                raise RuntimeError(
                    f"Module `iwp_build` is not available in python `{python_path}`. "
                    "Install iwp tools first, for example: `python -m pip install iwp-build iwp-lint`."
                )
            command_records: list[dict[str, Any]] = []
            await self._run_command(
                task_id=task_id,
                python_path=python_path,
                plugin_root=plugin_root,
                args=["session", "current", "--config", ".iwp-lint.yaml", "--preset", "agent-default"],
                command_records=command_records,
                required=False,
                stage="session_bootstrap",
                message="Checking current IWP session",
            )
            start_result = await self._run_command(
                task_id=task_id,
                python_path=python_path,
                plugin_root=plugin_root,
                args=[
                    "session",
                    "start",
                    "--config",
                    ".iwp-lint.yaml",
                    "--preset",
                    "agent-default",
                    "--json",
                    "out/session-start.json",
                ],
                command_records=command_records,
                required=False,
                stage="session_bootstrap",
                message="Starting IWP session",
            )
            start_output = f"{start_result.get('stdout', '')}\n{start_result.get('stderr', '')}".lower()
            if int(start_result.get("exit_code") or 0) != 0 and "open session already exists" not in start_output:
                raise RuntimeError(start_result.get("stderr") or start_result.get("stdout") or "session start failed")
            await self._run_command(
                task_id=task_id,
                python_path=python_path,
                plugin_root=plugin_root,
                args=[
                    "session",
                    "diff",
                    "--config",
                    ".iwp-lint.yaml",
                    "--preset",
                    "agent-default",
                ],
                command_records=command_records,
                required=True,
                stage="session_diff",
                message="Running IWP session diff",
            )
            await self._run_command(
                task_id=task_id,
                python_path=python_path,
                plugin_root=plugin_root,
                args=[
                    "session",
                    "reconcile",
                    "--config",
                    ".iwp-lint.yaml",
                    "--preset",
                    "agent-default",
                ],
                command_records=command_records,
                required=True,
                stage="session_reconcile",
                message="Running IWP session reconcile",
            )
            result = {
                "commands": command_records,
                "session_diff": self._read_json_if_exists(plugin_root / "out" / "session-diff.json"),
                "session_reconcile": self._read_json_if_exists(plugin_root / "out" / "session-reconcile.json"),
            }
            await self._update_task(
                task_id,
                status="completed",
                stage="completed",
                message="IWP build finished",
                completed_at=datetime.now().isoformat(),
                result=result,
                error=None,
            )
        except Exception as err:
            logger.error("IWP build task failed: plugin=%s task=%s err=%s", plugin_id, task_id, err, exc_info=True)
            await self._update_task(
                task_id,
                status="failed",
                stage="failed",
                message="IWP build failed",
                completed_at=datetime.now().isoformat(),
                error=str(err),
            )

    async def _run_command(
        self,
        *,
        task_id: str,
        python_path: Path,
        plugin_root: Path,
        args: list[str],
        command_records: list[dict[str, Any]],
        required: bool,
        stage: str,
        message: str,
    ) -> dict[str, Any]:
        await self._update_task(
            task_id,
            stage=stage,
            message=message,
        )
        command = [str(python_path), "-m", "iwp_build.cli", *args]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(plugin_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_data, stderr_data = await process.communicate()
        exit_code = int(process.returncode or 0)
        result = {
            "command": command,
            "cwd": str(plugin_root),
            "exit_code": exit_code,
            "stdout": stdout_data.decode("utf-8", errors="replace"),
            "stderr": stderr_data.decode("utf-8", errors="replace"),
            "stage": stage,
        }
        command_records.append(result)
        if required and exit_code != 0:
            raise RuntimeError(result["stderr"] or result["stdout"] or f"command failed: {' '.join(args)}")
        return result

    async def _update_task(
        self,
        task_id: str | None,
        *,
        status: str | None = None,
        stage: str | None = None,
        message: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if not task_id:
            return
        async with self._task_lock:
            payload = self._build_tasks.get(task_id)
            if payload is None:
                return
            if status is not None:
                payload["status"] = status
            if stage is not None:
                payload["stage"] = stage
            if message is not None:
                payload["message"] = message
            if started_at is not None:
                payload["started_at"] = started_at
            if completed_at is not None:
                payload["completed_at"] = completed_at
            if result is not None:
                payload["result"] = result
            if error is not None:
                payload["error"] = error
            payload["updated_at"] = datetime.now().isoformat()

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

    @staticmethod
    def _resolve_python() -> Path:
        python_path = Config.get_pbs_python()
        if python_path is not None and python_path.exists():
            return python_path
        fallback = Path(sys.executable).expanduser().resolve()
        if fallback.exists():
            return fallback
        raise RuntimeError("Python runtime is not available")

    def _resolve_plugin_root(self, plugin_id: str) -> Path:
        plugin_path = self._get_plugin_path(plugin_id)
        if not plugin_path:
            raise RuntimeError(f"Plugin path not found: {plugin_id}")
        root = Path(plugin_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise RuntimeError(f"Plugin source directory not found: {plugin_id}")
        return root

    def _resolve_iwp_root(self, plugin_id: str) -> Path:
        root = self._resolve_plugin_root(plugin_id)
        iwp_root = (root / "InstructWare.iw").resolve()
        if not iwp_root.exists() or not iwp_root.is_dir():
            raise RuntimeError(f"InstructWare.iw not found for plugin: {plugin_id}")
        return iwp_root

    @staticmethod
    def _resolve_markdown_path(iwp_root: Path, relative_path: str) -> Path:
        normalized = str(relative_path or "").strip().replace("\\", "/")
        if not normalized:
            raise RuntimeError("Markdown file path is required")
        if normalized.startswith("../") or normalized.startswith("/"):
            raise RuntimeError("Invalid markdown path")
        target = (iwp_root / normalized).resolve()
        try:
            target.relative_to(iwp_root)
        except ValueError as err:
            raise RuntimeError("Markdown path must stay inside InstructWare.iw") from err
        if target.suffix.lower() != ".md":
            raise RuntimeError("Only markdown files are supported")
        return target

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
        if not path.exists() or not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {"value": data}
        except Exception:
            logger.warning("Failed to parse JSON artifact: %s", path, exc_info=True)
            return None
