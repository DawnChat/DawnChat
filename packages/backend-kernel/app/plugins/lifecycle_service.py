from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any
import uuid

from app.services.task_manager import TaskStatus, get_task_manager
from app.utils.logger import get_logger
from app.voice import get_tts_runtime_service

from . import get_plugin_manager
from .lifecycle_contract import (
    STAGE_LABELS,
    LifecycleOperationType,
    LifecycleProgress,
    LifecycleStage,
)

logger = get_logger("plugin_lifecycle_service")


@dataclass
class LifecycleOperation:
    task_id: str
    operation_type: LifecycleOperationType
    plugin_id: str = ""
    app_type: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    progress: LifecycleProgress = field(
        default_factory=lambda: LifecycleProgress(
            stage=LifecycleStage.VALIDATE_INPUT,
            progress=0,
            message="任务排队中",
        )
    )
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    def to_dict(self, task_status: dict[str, Any] | None = None) -> dict[str, Any]:
        status = str((task_status or {}).get("status") or "pending")
        elapsed_seconds = 0
        if task_status and task_status.get("started_at"):
            try:
                started = datetime.fromisoformat(str(task_status["started_at"]))
                elapsed_seconds = int((datetime.now(started.tzinfo or timezone.utc) - started).total_seconds())
            except Exception:
                elapsed_seconds = 0
        return {
            "task_id": self.task_id,
            "operation_type": self.operation_type.value,
            "plugin_id": self.plugin_id,
            "app_type": self.app_type,
            "status": status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elapsed_seconds": elapsed_seconds,
            "progress": self.progress.to_dict(),
            "result": self.result,
            "error": self.error,
        }


class PluginLifecycleService:
    def __init__(self) -> None:
        self._operations: dict[str, LifecycleOperation] = {}
        self._eta_history: dict[tuple[str, str], list[float]] = {}

    def _touch(self, task_id: str) -> None:
        op = self._operations[task_id]
        op.updated_at = datetime.now(timezone.utc).isoformat()

    def _set_progress(
        self,
        task_id: str,
        *,
        stage: LifecycleStage,
        progress: int,
        message: str,
        retryable: bool = False,
        details: list[str] | None = None,
        stage_started_at: float | None = None,
    ) -> None:
        op = self._operations[task_id]
        eta_seconds = None
        if stage_started_at is not None:
            elapsed = max(0.1, time.monotonic() - stage_started_at)
            key = (op.operation_type.value, stage.value)
            history = self._eta_history.setdefault(key, [])
            if progress > 0 and progress < 100:
                eta_seconds = int((elapsed / max(1, progress)) * max(1, 100 - progress))
            history.append(elapsed)
            self._eta_history[key] = history[-20:]
        op.progress = LifecycleProgress(
            stage=stage,
            stage_label=STAGE_LABELS.get(stage, stage.value),
            progress=progress,
            message=message,
            retryable=retryable,
            details=details or [],
            eta_seconds=eta_seconds,
        )
        self._touch(task_id)

    async def _set_task_progress(self, task_id: str, progress: int, message: str) -> None:
        task_manager = get_task_manager()
        await task_manager.update_progress(task_id, max(0.0, min(1.0, progress / 100.0)), message)

    async def submit_create_dev_session(self, payload: dict[str, Any]) -> str:
        plugin_id_hint = str(payload.get("plugin_id") or "")
        task_manager = get_task_manager()

        async def _executor() -> dict[str, Any]:
            manager = get_plugin_manager()
            stage_started = time.monotonic()
            self._set_progress(task_id, stage=LifecycleStage.VALIDATE_INPUT, progress=5, message="校验创建参数")
            await self._set_task_progress(task_id, 5, "校验创建参数")
            required = ("template_id", "app_type", "name", "plugin_id", "owner_email", "owner_user_id")
            missing = [item for item in required if not str(payload.get(item) or "").strip()]
            if missing:
                raise ValueError(f"Missing required fields: {', '.join(missing)}")

            self._set_progress(
                task_id,
                stage=LifecycleStage.ENSURE_TEMPLATE_CACHE,
                progress=12,
                message="检查模板缓存",
                stage_started_at=stage_started,
            )
            await self._set_task_progress(task_id, 12, "检查模板缓存")
            await manager.ensure_template_cached(str(payload["template_id"]), force_refresh=True)

            stage_started = time.monotonic()
            self._set_progress(
                task_id,
                stage=LifecycleStage.SCAFFOLD_SOURCE,
                progress=30,
                message="创建插件源码",
                stage_started_at=stage_started,
            )
            await self._set_task_progress(task_id, 30, "创建插件源码")
            created = await manager.scaffold_plugin_from_template(
                template_id=str(payload["template_id"]),
                app_name=str(payload["name"]),
                app_description=str(payload.get("description") or ""),
                desired_id=str(payload["plugin_id"]),
                owner_email=str(payload["owner_email"]),
                owner_user_id=str(payload["owner_user_id"]),
                app_type=str(payload["app_type"]),
                source_type=(
                    "official_user_main_assistant"
                    if bool(payload.get("is_main_assistant"))
                    else "user_created"
                ),
                is_main_assistant=bool(payload.get("is_main_assistant")),
            )
            plugin_id = str(created.get("plugin_id") or "")
            if plugin_id:
                self._operations[task_id].plugin_id = plugin_id
            app_type = str(payload.get("app_type") or "desktop")
            self._operations[task_id].app_type = app_type

            stage_started = time.monotonic()
            if app_type == "desktop":
                self._set_progress(
                    task_id,
                    stage=LifecycleStage.PREPARE_PYTHON_RUNTIME,
                    progress=50,
                    message="准备 Python 运行时",
                    stage_started_at=stage_started,
                )
                await self._set_task_progress(task_id, 50, "准备 Python 运行时")
            else:
                self._set_progress(
                    task_id,
                    stage=LifecycleStage.PREPARE_FRONTEND_RUNTIME,
                    progress=50,
                    message="准备前端运行时",
                    stage_started_at=stage_started,
                )
                await self._set_task_progress(task_id, 50, "准备前端运行时")
            await manager.prepare_plugin_runtime(plugin_id)

            self._set_progress(task_id, stage=LifecycleStage.START_PREVIEW_BACKEND, progress=72, message="启动开发预览")
            await self._set_task_progress(task_id, 72, "启动开发预览")
            preview_url = await manager.start_plugin_preview(plugin_id)
            if not preview_url:
                raise RuntimeError("Failed to start preview")

            self._set_progress(task_id, stage=LifecycleStage.WAIT_PREVIEW_READY, progress=90, message="等待预览就绪")
            await self._set_task_progress(task_id, 90, "等待预览就绪")
            ready = await self._wait_preview_ready(plugin_id, timeout_seconds=90)
            if not ready:
                raise RuntimeError("Preview not ready within timeout")

            self._set_progress(task_id, stage=LifecycleStage.FINALIZE, progress=100, message="创建完成")
            await self._set_task_progress(task_id, 100, "创建完成")
            result = {
                "plugin_id": plugin_id,
                "app_type": app_type,
                "preview_url": ready.get("url") if isinstance(ready, dict) else preview_url,
            }
            op = self._operations[task_id]
            op.result = result
            return result

        task_id = str(uuid.uuid4())[:8]
        self._operations[task_id] = LifecycleOperation(
            task_id=task_id,
            operation_type=LifecycleOperationType.CREATE_DEV_SESSION,
            plugin_id=plugin_id_hint,
            app_type=str(payload.get("app_type") or ""),
        )
        try:
            await task_manager.submit(
                tool_name="plugin_lifecycle_create_dev_session",
                arguments={},
                plugin_id=plugin_id_hint or "host",
                executor_func=lambda: _executor(),
                metadata={"domain": "plugin_lifecycle", "operation": LifecycleOperationType.CREATE_DEV_SESSION.value},
                task_id=task_id,
            )
        except Exception:
            self._operations.pop(task_id, None)
            raise
        return task_id

    async def submit_start_dev_session(self, plugin_id: str) -> str:
        task_manager = get_task_manager()

        async def _executor() -> dict[str, Any]:
            manager = get_plugin_manager()
            plugin = manager.get_plugin_snapshot(plugin_id)
            if plugin is None:
                raise RuntimeError(f"Plugin not found: {plugin_id}")
            app_type = str(plugin.get("app_type") or "desktop")
            self._operations[task_id].app_type = app_type

            self._set_progress(task_id, stage=LifecycleStage.VALIDATE_INPUT, progress=8, message="校验插件状态")
            await self._set_task_progress(task_id, 8, "校验插件状态")
            self._set_progress(task_id, stage=LifecycleStage.PREPARE_FRONTEND_RUNTIME, progress=45, message="准备运行时")
            await self._set_task_progress(task_id, 45, "准备运行时")
            await manager.prepare_plugin_runtime(plugin_id)

            self._set_progress(task_id, stage=LifecycleStage.START_PREVIEW_BACKEND, progress=72, message="启动开发预览")
            await self._set_task_progress(task_id, 72, "启动开发预览")
            preview_url = await manager.start_plugin_preview(plugin_id)
            if not preview_url:
                raise RuntimeError("Failed to start preview")

            self._set_progress(task_id, stage=LifecycleStage.WAIT_PREVIEW_READY, progress=92, message="等待预览就绪")
            await self._set_task_progress(task_id, 92, "等待预览就绪")
            ready = await self._wait_preview_ready(plugin_id, timeout_seconds=90)
            if not ready:
                raise RuntimeError("Preview not ready within timeout")
            self._set_progress(task_id, stage=LifecycleStage.FINALIZE, progress=100, message="开发模式就绪")
            await self._set_task_progress(task_id, 100, "开发模式就绪")
            result = {
                "plugin_id": plugin_id,
                "app_type": app_type,
                "preview_url": ready.get("url") if isinstance(ready, dict) else preview_url,
            }
            self._operations[task_id].result = result
            return result

        task_id = str(uuid.uuid4())[:8]
        self._operations[task_id] = LifecycleOperation(
            task_id=task_id,
            operation_type=LifecycleOperationType.START_DEV_SESSION,
            plugin_id=plugin_id,
        )
        try:
            await task_manager.submit(
                tool_name="plugin_lifecycle_start_dev_session",
                arguments={},
                plugin_id=plugin_id,
                executor_func=lambda: _executor(),
                metadata={"domain": "plugin_lifecycle", "operation": LifecycleOperationType.START_DEV_SESSION.value},
                task_id=task_id,
            )
        except Exception:
            self._operations.pop(task_id, None)
            raise
        return task_id

    async def submit_restart_dev_session(self, plugin_id: str) -> str:
        task_manager = get_task_manager()

        async def _executor() -> dict[str, Any]:
            manager = get_plugin_manager()
            plugin = manager.get_plugin_snapshot(plugin_id)
            if plugin is None:
                raise RuntimeError(f"Plugin not found: {plugin_id}")
            app_type = str(plugin.get("app_type") or "desktop")
            self._operations[task_id].app_type = app_type

            self._set_progress(task_id, stage=LifecycleStage.VALIDATE_INPUT, progress=8, message="校验插件状态")
            await self._set_task_progress(task_id, 8, "校验插件状态")

            # Restart should always reset existing preview session first.
            self._set_progress(task_id, stage=LifecycleStage.START_PREVIEW_BACKEND, progress=22, message="停止旧预览实例")
            await self._set_task_progress(task_id, 22, "停止旧预览实例")
            stopped = await manager.stop_plugin_preview(plugin_id)
            if not stopped:
                raise RuntimeError("Failed to stop preview")
            await get_tts_runtime_service().reset_plugin(plugin_id)

            self._set_progress(task_id, stage=LifecycleStage.PREPARE_FRONTEND_RUNTIME, progress=45, message="准备运行时")
            await self._set_task_progress(task_id, 45, "准备运行时")
            await manager.prepare_plugin_runtime(plugin_id)

            self._set_progress(task_id, stage=LifecycleStage.START_PREVIEW_BACKEND, progress=72, message="启动开发预览")
            await self._set_task_progress(task_id, 72, "启动开发预览")
            preview_url = await manager.start_plugin_preview(plugin_id)
            if not preview_url:
                raise RuntimeError("Failed to start preview")

            self._set_progress(task_id, stage=LifecycleStage.WAIT_PREVIEW_READY, progress=92, message="等待预览就绪")
            await self._set_task_progress(task_id, 92, "等待预览就绪")
            ready = await self._wait_preview_ready(plugin_id, timeout_seconds=90)
            if not ready:
                raise RuntimeError("Preview not ready within timeout")
            self._set_progress(task_id, stage=LifecycleStage.FINALIZE, progress=100, message="重启完成")
            await self._set_task_progress(task_id, 100, "重启完成")
            result = {
                "plugin_id": plugin_id,
                "app_type": app_type,
                "preview_url": ready.get("url") if isinstance(ready, dict) else preview_url,
            }
            self._operations[task_id].result = result
            return result

        task_id = str(uuid.uuid4())[:8]
        self._operations[task_id] = LifecycleOperation(
            task_id=task_id,
            operation_type=LifecycleOperationType.RESTART_DEV_SESSION,
            plugin_id=plugin_id,
        )
        try:
            await task_manager.submit(
                tool_name="plugin_lifecycle_restart_dev_session",
                arguments={},
                plugin_id=plugin_id,
                executor_func=lambda: _executor(),
                metadata={"domain": "plugin_lifecycle", "operation": LifecycleOperationType.RESTART_DEV_SESSION.value},
                task_id=task_id,
            )
        except Exception:
            self._operations.pop(task_id, None)
            raise
        return task_id

    async def submit_start_runtime(self, plugin_id: str) -> str:
        task_manager = get_task_manager()

        async def _executor() -> dict[str, Any]:
            manager = get_plugin_manager()
            plugin = manager.get_plugin_snapshot(plugin_id)
            if plugin is None:
                raise RuntimeError(f"Plugin not found: {plugin_id}")
            app_type = str(plugin.get("app_type") or "desktop")
            self._operations[task_id].app_type = app_type

            self._set_progress(task_id, stage=LifecycleStage.VALIDATE_INPUT, progress=10, message="校验插件状态")
            await self._set_task_progress(task_id, 10, "校验插件状态")
            self._set_progress(task_id, stage=LifecycleStage.START_RUNTIME, progress=60, message="启动应用")
            await self._set_task_progress(task_id, 60, "启动应用")
            port = await manager.start_plugin(plugin_id)
            if not port:
                raise RuntimeError("Failed to start runtime")
            self._set_progress(task_id, stage=LifecycleStage.FINALIZE, progress=100, message="启动完成")
            await self._set_task_progress(task_id, 100, "启动完成")
            result = {"plugin_id": plugin_id, "app_type": app_type, "port": port}
            self._operations[task_id].result = result
            return result

        task_id = str(uuid.uuid4())[:8]
        self._operations[task_id] = LifecycleOperation(
            task_id=task_id,
            operation_type=LifecycleOperationType.START_RUNTIME,
            plugin_id=plugin_id,
        )
        try:
            await task_manager.submit(
                tool_name="plugin_lifecycle_start_runtime",
                arguments={},
                plugin_id=plugin_id,
                executor_func=lambda: _executor(),
                metadata={"domain": "plugin_lifecycle", "operation": LifecycleOperationType.START_RUNTIME.value},
                task_id=task_id,
            )
        except Exception:
            self._operations.pop(task_id, None)
            raise
        return task_id

    def get_operation(self, task_id: str) -> dict[str, Any] | None:
        op = self._operations.get(task_id)
        if op is None:
            return None
        task_status = get_task_manager().get_task_status(task_id)
        if task_status:
            status = str(task_status.get("status") or "")
            if status == TaskStatus.FAILED.value:
                op.progress.stage = LifecycleStage.FAILED
                op.progress.stage_label = STAGE_LABELS[LifecycleStage.FAILED]
                op.progress.retryable = True
                op.error = {
                    "message": str(task_status.get("error") or "Task failed"),
                    "code": str(task_status.get("error_code") or "TASK_EXECUTION_ERROR"),
                }
            elif status == TaskStatus.CANCELLED.value:
                op.progress.stage = LifecycleStage.CANCELLED
                op.progress.stage_label = STAGE_LABELS[LifecycleStage.CANCELLED]
        return op.to_dict(task_status)

    async def cancel_operation(self, task_id: str) -> bool:
        ok = await get_task_manager().cancel_task(task_id)
        if ok and task_id in self._operations:
            op = self._operations[task_id]
            op.progress = LifecycleProgress(
                stage=LifecycleStage.CANCELLED,
                progress=min(99, op.progress.progress),
                message="任务已取消",
                stage_label=STAGE_LABELS[LifecycleStage.CANCELLED],
            )
            self._touch(task_id)
        return ok

    async def _wait_preview_ready(self, plugin_id: str, *, timeout_seconds: int) -> dict[str, Any] | None:
        manager = get_plugin_manager()
        deadline = time.monotonic() + max(1, timeout_seconds)
        while time.monotonic() < deadline:
            status = manager.get_plugin_preview_status(plugin_id) or {}
            state = str(status.get("state") or "")
            frontend_mode = str(status.get("frontend_mode") or "")
            frontend_reachable = status.get("frontend_reachable")
            if (
                state == "running"
                and status.get("url")
                and not (frontend_mode == "dev" and frontend_reachable is False)
            ):
                return status
            if state == "error":
                raise RuntimeError(str(status.get("error_message") or "Preview start failed"))
            await asyncio.sleep(1.0)
        return None


_lifecycle_service: PluginLifecycleService | None = None


def get_plugin_lifecycle_service() -> PluginLifecycleService:
    global _lifecycle_service
    if _lifecycle_service is None:
        _lifecycle_service = PluginLifecycleService()
    return _lifecycle_service
