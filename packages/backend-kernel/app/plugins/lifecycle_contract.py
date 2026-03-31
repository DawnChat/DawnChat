from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LifecycleOperationType(str, Enum):
    CREATE_DEV_SESSION = "create_dev_session"
    START_DEV_SESSION = "start_dev_session"
    RESTART_DEV_SESSION = "restart_dev_session"
    START_RUNTIME = "start_runtime"


class LifecycleStage(str, Enum):
    VALIDATE_INPUT = "validate_input"
    ENSURE_TEMPLATE_CACHE = "ensure_template_cache"
    SCAFFOLD_SOURCE = "scaffold_source"
    PREPARE_PYTHON_RUNTIME = "prepare_python_runtime"
    PREPARE_FRONTEND_RUNTIME = "prepare_frontend_runtime"
    START_PREVIEW_BACKEND = "start_preview_backend"
    START_PREVIEW_FRONTEND = "start_preview_frontend"
    WAIT_PREVIEW_READY = "wait_preview_ready"
    START_RUNTIME = "start_runtime"
    FINALIZE = "finalize"
    FAILED = "failed"
    CANCELLED = "cancelled"


STAGE_LABELS: dict[LifecycleStage, str] = {
    LifecycleStage.VALIDATE_INPUT: "校验输入",
    LifecycleStage.ENSURE_TEMPLATE_CACHE: "准备模板缓存",
    LifecycleStage.SCAFFOLD_SOURCE: "创建插件源码",
    LifecycleStage.PREPARE_PYTHON_RUNTIME: "准备 Python 运行时",
    LifecycleStage.PREPARE_FRONTEND_RUNTIME: "准备前端运行时",
    LifecycleStage.START_PREVIEW_BACKEND: "启动预览后端",
    LifecycleStage.START_PREVIEW_FRONTEND: "启动预览前端",
    LifecycleStage.WAIT_PREVIEW_READY: "等待预览就绪",
    LifecycleStage.START_RUNTIME: "启动应用",
    LifecycleStage.FINALIZE: "完成",
    LifecycleStage.FAILED: "失败",
    LifecycleStage.CANCELLED: "已取消",
}


@dataclass
class LifecycleProgress:
    stage: LifecycleStage
    progress: int
    message: str
    stage_label: str = ""
    eta_seconds: int | None = None
    retryable: bool = False
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "stage_label": self.stage_label or STAGE_LABELS.get(self.stage, self.stage.value),
            "progress": int(max(0, min(100, self.progress))),
            "message": self.message,
            "eta_seconds": self.eta_seconds,
            "retryable": self.retryable,
            "details": list(self.details),
        }

