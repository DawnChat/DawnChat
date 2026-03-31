"""
DawnChat - API 路由（主路由）

职责：聚合所有子路由模块
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api import ai_routes, cloud_models_routes, sdk_routes
from app.utils.logger import get_logger

# 创建主路由器
router = APIRouter()

# 注册子路由
router.include_router(ai_routes.router, tags=["ai"])
router.include_router(cloud_models_routes.router, prefix="/cloud", tags=["cloud-models"])
router.include_router(sdk_routes.router, tags=["sdk"])

frontend_logger = get_logger("frontend")


class FrontendLogEntry(BaseModel):
    level: str = Field(..., min_length=1, max_length=16)
    message: str = Field(..., min_length=1)
    data: Optional[Any] = None
    timestamp: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class FrontendLogBatch(BaseModel):
    logs: list[FrontendLogEntry] = Field(default_factory=list)


@router.get("/frontend/health")
async def frontend_health():
    return {"status": "ok", "name": "DawnChat"}


@router.post("/frontend/logs")
async def ingest_frontend_logs(batch: FrontendLogBatch):
    received = 0
    for entry in batch.logs:
        level = entry.level.upper()
        prefix_parts = ["FE"]
        if entry.timestamp:
            prefix_parts.append(entry.timestamp)
        if isinstance(entry.meta, dict):
            runtime = entry.meta.get("runtime")
            if isinstance(runtime, str) and runtime:
                prefix_parts.append(runtime)
            session_id = entry.meta.get("session_id")
            if isinstance(session_id, str) and session_id:
                prefix_parts.append(f"sid={session_id[:8]}")

        prefix = f"[{' '.join(prefix_parts)}]"

        msg = f"{prefix} {entry.message}"
        if entry.data is not None:
            try:
                payload = json.dumps(entry.data, ensure_ascii=False, default=str)
            except Exception:
                payload = str(entry.data)
            msg = f"{msg}\n{payload}"

        if level == "ERROR":
            frontend_logger.error(msg)
        elif level in ("WARN", "WARNING"):
            frontend_logger.warning(msg)
        elif level == "DEBUG":
            frontend_logger.debug(msg)
        else:
            frontend_logger.info(msg)
        received += 1

    return {"success": True, "received": received}
