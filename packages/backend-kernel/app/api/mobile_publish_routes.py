from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.plugins import get_plugin_manager
from app.services.mobile_publish_service import MobilePublishError, get_mobile_publish_service

router = APIRouter(prefix="/mobile-publish", tags=["mobile-publish"])


class MobilePublishRequest(BaseModel):
    supabase_access_token: str
    version: str | None = None


class MobilePublishRefreshRequest(BaseModel):
    supabase_access_token: str


def _error_response(error: MobilePublishError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
        },
    )


@router.post("/{plugin_id}")
async def publish_mobile_plugin(plugin_id: str, request: MobilePublishRequest):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "mobile_publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    if str(plugin.get("app_type") or "desktop") != "mobile":
        return JSONResponse(status_code=400, content={"code": "mobile_publish_plugin_not_mobile", "message": "Only mobile plugins can be published"})
    try:
        payload = await get_mobile_publish_service().start_publish_task(
            plugin_id=plugin_id,
            supabase_access_token=request.supabase_access_token,
            version=request.version,
        )
        return {"status": "success", "data": payload}
    except MobilePublishError as error:
        return _error_response(error)


@router.get("/{plugin_id}/status")
async def get_mobile_publish_status(plugin_id: str):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "mobile_publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    try:
        payload = await get_mobile_publish_service().get_publish_status(plugin_id)
        return {"status": "success", "data": payload}
    except MobilePublishError as error:
        return _error_response(error)


@router.get("/{plugin_id}/tasks/{task_id}")
async def get_mobile_publish_task(plugin_id: str, task_id: str):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "mobile_publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    try:
        payload = get_mobile_publish_service().get_publish_task(plugin_id, task_id)
        return {"status": "success", "data": payload}
    except MobilePublishError as error:
        return _error_response(error)


@router.post("/{plugin_id}/refresh-share")
async def refresh_mobile_share_payload(plugin_id: str, request: MobilePublishRefreshRequest):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "mobile_publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    try:
        payload = await get_mobile_publish_service().refresh_share_payload(plugin_id, request.supabase_access_token)
        return {"status": "success", "data": payload}
    except MobilePublishError as error:
        return _error_response(error)
