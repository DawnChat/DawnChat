"""
OpenCode 控制面路由

仅负责进程与配置控制，不代理会话消息数据面。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.services.agent_catalog_service import get_agent_catalog_service
from app.services.coding_agent_workspace_resolver import (
    WorkspaceResolveError,
    resolve_coding_agent_workspace,
)
from app.services.opencode_manager import OpenCodeUnavailableError, get_opencode_manager
from app.storage import storage_manager
from app.utils.logger import api_logger as logger

router = APIRouter(prefix="/opencode", tags=["opencode"])


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


def _provider_aliases(provider_id: str) -> tuple[str, ...]:
    normalized = (provider_id or "").strip().lower()
    if normalized == "gemini":
        return ("gemini", "google")
    if normalized == "google":
        return ("google", "gemini")
    return (normalized,) if normalized else tuple()


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
async def start_opencode_with_workspace(request: StartWithWorkspaceRequest) -> Dict[str, Any]:
    manager = get_opencode_manager()
    logger.info(
        "OpenCode start_with_workspace request: requested_kind=%s requested_plugin_id=%s requested_project_id=%s force_restart=%s current_workspace=%s current_startup_context=%s",
        request.workspace_kind,
        request.plugin_id,
        request.project_id,
        request.force_restart,
        manager.workspace_path,
        manager.startup_context,
    )
    try:
        resolved = resolve_coding_agent_workspace(
            workspace_kind=request.workspace_kind,
            plugin_id=request.plugin_id,
            project_id=request.project_id,
        )
    except WorkspaceResolveError as err:
        raise HTTPException(status_code=err.status_code, detail=str(err)) from err
    workspace_path = resolved.workspace_path
    startup_context = resolved.startup_context
    instruction_policy = resolved.instruction_policy
    workspace_profile = startup_context.get("workspace_profile") or {}
    rules_status: Dict[str, Any] = {}
    try:
        rules_status = await get_opencode_rules_service().ensure_ready(
            force_refresh=request.force_rules_refresh
        )
    except Exception as err:
        # Shared rules sync should not block OpenCode startup.
        logger.warning("OpenCode shared rules sync failed, continue with local fallback: %s", err)
        rules_status = {
            "enabled": False,
            "reason": "sync_failed",
            "error": str(err),
        }
    ok = await manager.start(
        workspace_path=workspace_path,
        force_restart=request.force_restart,
        startup_context=startup_context,
        instruction_policy=instruction_policy,
    )
    if not ok:
        health_payload = await manager.get_health_payload()
        raise HTTPException(
            status_code=500,
            detail={
                "message": "OpenCode 启动失败",
                "reason": "start_with_workspace_failed",
                "workspace_path": workspace_path,
                "health": health_payload,
                "last_start_failure": manager.last_start_failure,
            },
        )
    health_payload = await manager.get_health_payload()
    health_payload["rules"] = rules_status
    health_payload["workspace_profile"] = workspace_profile
    logger.info(
        "OpenCode start_with_workspace resolved: workspace_path=%s startup_context=%s health_status=%s health_workspace=%s",
        workspace_path,
        startup_context,
        health_payload.get("status"),
        health_payload.get("workspace_path"),
    )
    return {"status": "success", "data": health_payload}


@router.post("/stop")
async def stop_opencode() -> Dict[str, Any]:
    manager = get_opencode_manager()
    await manager.stop()
    return {"status": "success"}


@router.get("/health")
async def opencode_health() -> Dict[str, Any]:
    manager = get_opencode_manager()
    return {"status": "success", "data": await manager.get_health_payload()}


@router.get("/diagnostics")
async def opencode_diagnostics() -> Dict[str, Any]:
    manager = get_opencode_manager()
    try:
        data = await manager.get_runtime_diagnostics()
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error("获取 OpenCode diagnostics 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/workspace")
async def opencode_workspace() -> Dict[str, Any]:
    manager = get_opencode_manager()
    return {
        "status": "success",
        "data": {
            "workspace_path": manager.workspace_path,
            "state": manager.status.value,
            "startup_context": manager.startup_context,
        },
    }


@router.get("/rules")
async def opencode_rules_status() -> Dict[str, Any]:
    return {"status": "success", "data": get_opencode_rules_service().get_status()}


@router.get("/config/providers")
async def opencode_config_providers() -> Dict[str, Any]:
    manager = get_opencode_manager()
    try:
        data = await manager.get_config_providers()
        providers = data.get("providers") if isinstance(data, dict) else None
        if isinstance(providers, list):
            for provider in providers:
                if not isinstance(provider, dict):
                    continue
                provider_id = str(provider.get("id") or provider.get("providerID") or "").strip()
                aliases = _provider_aliases(provider_id)
                configured = False
                for alias in aliases:
                    api_key = await storage_manager.get_api_key(alias)
                    if isinstance(api_key, str) and api_key.strip():
                        configured = True
                        break

                is_builtin = provider_id in {"dawnchat-local", "opencode"}
                provider["configured"] = configured or is_builtin
                provider["available"] = provider.get("available", True) and (configured or is_builtin)
        return {"status": "success", "data": data}
    except OpenCodeUnavailableError as e:
        logger.error("获取 OpenCode providers 失败(服务未就绪): %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except TimeoutError as e:
        logger.error("获取 OpenCode providers 超时: %s", e)
        raise HTTPException(status_code=504, detail="OpenCode providers 请求超时")
    except Exception as e:
        if e.__class__.__name__ == "ReadTimeout":
            logger.error("获取 OpenCode providers 超时: %s", e)
            raise HTTPException(status_code=504, detail="OpenCode providers 请求超时")
        logger.error("获取 OpenCode providers 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("/config")
async def opencode_patch_config(request: PatchConfigRequest) -> Dict[str, Any]:
    manager = get_opencode_manager()
    patch = _validate_patch_payload(request)
    try:
        data = await manager.patch_config(patch)
        return {"status": "success", "data": data}
    except OpenCodeUnavailableError as e:
        logger.error("Patch OpenCode 配置失败(服务未就绪): %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Patch OpenCode 配置失败: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/agents")
async def opencode_agents() -> Dict[str, Any]:
    manager = get_opencode_manager()
    try:
        data = await manager.list_agents()
        return {"status": "success", "data": data}
    except OpenCodeUnavailableError as e:
        logger.error("获取 OpenCode agents 失败(服务未就绪): %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except TimeoutError as e:
        logger.error("获取 OpenCode agents 超时: %s", e)
        raise HTTPException(status_code=504, detail="OpenCode agents 请求超时")
    except Exception as e:
        if e.__class__.__name__ == "ReadTimeout":
            logger.error("获取 OpenCode agents 超时: %s", e)
            raise HTTPException(status_code=504, detail="OpenCode agents 请求超时")
        logger.error("获取 OpenCode agents 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=str(e))
