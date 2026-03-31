from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import Config
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.services.agent_catalog_service import get_agent_catalog_service
from app.services.claude_manager import ClaudeUnavailableError, get_claude_manager
from app.services.coding_agent_workspace_resolver import (
    WorkspaceResolveError,
    resolve_coding_agent_workspace,
)
from app.utils.logger import api_logger as logger

router = APIRouter(prefix="/claude", tags=["claude"])


class PatchConfigRequest(BaseModel):
    model: Optional[str] = None
    default_agent: Optional[str] = None
    provider: Optional[Dict[str, Any]] = Field(default=None)


class StartWithWorkspaceRequest(BaseModel):
    workspace_kind: str = "plugin-dev"
    plugin_id: Optional[str] = None
    project_id: Optional[str] = None
    session_title: Optional[str] = None
    force_restart: bool = False
    force_rules_refresh: bool = False


def _ensure_enabled() -> None:
    if Config.CLAUDE_ENABLED:
        return
    raise HTTPException(status_code=503, detail="feature_disabled: claude control plane is disabled")


def _validate_patch_payload(req: PatchConfigRequest) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if req.model is not None:
        patch["model"] = req.model
    if req.default_agent is not None:
        candidate = str(req.default_agent).strip()
        if not candidate:
            raise HTTPException(status_code=400, detail="default_agent 不能为空")
        if not get_agent_catalog_service().is_primary_visible(candidate):
            raise HTTPException(status_code=400, detail=f"default_agent 不可用或不可见: {candidate}")
        patch["default_agent"] = candidate
    if req.provider is not None:
        patch["provider"] = req.provider
    if not patch:
        raise HTTPException(status_code=400, detail="PATCH 请求为空")
    return patch


@router.post("/start_with_workspace")
async def start_claude_with_workspace(request: StartWithWorkspaceRequest) -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    try:
        resolved = resolve_coding_agent_workspace(
            workspace_kind=request.workspace_kind,
            plugin_id=request.plugin_id,
            project_id=request.project_id,
        )
    except WorkspaceResolveError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from err
    workspace_profile = resolved.startup_context.get("workspace_profile") or {}
    rules_status: Dict[str, Any] = {}
    rules_dir: Optional[str] = None
    try:
        rules_status = await get_opencode_rules_service().ensure_ready(
            force_refresh=request.force_rules_refresh
        )
        rules_dir = str(rules_status.get("current_dir") or "").strip() or None
    except Exception as err:
        logger.warning("Claude shared rules sync failed, continue with local fallback: %s", err)
        rules_status = {
            "enabled": False,
            "reason": "sync_failed",
            "error": str(err),
        }
        rules_dir = get_opencode_rules_service().get_current_dir()
    try:
        ok = await manager.start(
            workspace_path=resolved.workspace_path,
            force_restart=request.force_restart,
            startup_context=resolved.startup_context,
            instruction_policy=resolved.instruction_policy,
            rules_dir=rules_dir,
        )
    except ClaudeUnavailableError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err
    if not ok:
        raise HTTPException(status_code=500, detail="Claude 启动失败")
    health_payload = await manager.get_health_payload()
    health_payload["rules"] = rules_status
    health_payload["workspace_profile"] = workspace_profile
    return {"status": "success", "data": health_payload}


@router.post("/stop")
async def stop_claude() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    await manager.stop()
    return {"status": "success"}


@router.get("/health")
async def claude_health() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    return {"status": "success", "data": await manager.get_health_payload()}


@router.get("/diagnostics")
async def claude_diagnostics() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    try:
        data = await manager.get_runtime_diagnostics()
        return {"status": "success", "data": data}
    except Exception as err:
        logger.error("获取 Claude diagnostics 失败: %s", err, exc_info=True)
        raise HTTPException(status_code=502, detail=str(err))


@router.get("/workspace")
async def claude_workspace() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    return {
        "status": "success",
        "data": {
            "workspace_path": manager.workspace_path,
            "state": manager.status.value,
        },
    }


@router.get("/rules")
async def claude_rules_status() -> Dict[str, Any]:
    _ensure_enabled()
    return {"status": "success", "data": get_opencode_rules_service().get_status()}


@router.get("/config/providers")
async def claude_config_providers() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    try:
        data = await manager.get_config_providers()
        return {"status": "success", "data": data}
    except ClaudeUnavailableError as err:
        logger.error("获取 Claude providers 失败(服务未就绪): %s", err)
        raise HTTPException(status_code=503, detail=str(err))
    except TimeoutError as err:
        logger.error("获取 Claude providers 超时: %s", err)
        raise HTTPException(status_code=504, detail="Claude providers 请求超时")
    except Exception as err:
        if err.__class__.__name__ == "ReadTimeout":
            logger.error("获取 Claude providers 超时: %s", err)
            raise HTTPException(status_code=504, detail="Claude providers 请求超时")
        logger.error("获取 Claude providers 失败: %s", err, exc_info=True)
        raise HTTPException(status_code=502, detail=str(err))


@router.patch("/config")
async def claude_patch_config(request: PatchConfigRequest) -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    patch = _validate_patch_payload(request)
    try:
        data = await manager.patch_config(patch)
        return {"status": "success", "data": data}
    except ClaudeUnavailableError as err:
        logger.error("Patch Claude 配置失败(服务未就绪): %s", err)
        raise HTTPException(status_code=503, detail=str(err))
    except Exception as err:
        logger.error("Patch Claude 配置失败: %s", err, exc_info=True)
        raise HTTPException(status_code=502, detail=str(err))


@router.get("/agents")
async def claude_agents() -> Dict[str, Any]:
    _ensure_enabled()
    manager = get_claude_manager()
    try:
        data = await manager.list_agents()
        return {"status": "success", "data": data}
    except ClaudeUnavailableError as err:
        logger.error("获取 Claude agents 失败(服务未就绪): %s", err)
        raise HTTPException(status_code=503, detail=str(err))
    except TimeoutError as err:
        logger.error("获取 Claude agents 超时: %s", err)
        raise HTTPException(status_code=504, detail="Claude agents 请求超时")
    except Exception as err:
        if err.__class__.__name__ == "ReadTimeout":
            logger.error("获取 Claude agents 超时: %s", err)
            raise HTTPException(status_code=504, detail="Claude agents 请求超时")
        logger.error("获取 Claude agents 失败: %s", err, exc_info=True)
        raise HTTPException(status_code=502, detail=str(err))
