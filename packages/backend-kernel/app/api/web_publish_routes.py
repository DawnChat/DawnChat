from __future__ import annotations

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.plugins import get_plugin_manager
from app.services.web_publish_service import WebPublishError, get_web_publish_service

router = APIRouter(prefix="/web-publish", tags=["web-publish"])


class WebPublishRequest(BaseModel):
    supabase_access_token: str
    slug: str | None = None
    title: str | None = None
    description: str | None = None
    version: str | None = None
    initial_visibility: str | None = None


def _extract_bearer_token(authorization: str | None) -> str | None:
    raw = str(authorization or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        return raw[7:].strip() or None
    return raw


def _error_response(error: WebPublishError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": error.code,
            "message": error.message,
        },
    )


@router.post("/{plugin_id}")
async def publish_web_plugin(plugin_id: str, request: WebPublishRequest):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    if str(plugin.get("app_type") or "desktop") != "web":
        return JSONResponse(status_code=400, content={"code": "publish_plugin_not_web", "message": "Only web plugins can be published"})
    try:
        payload = await get_web_publish_service().start_publish_task(
            plugin_id=plugin_id,
            supabase_access_token=request.supabase_access_token,
            slug=request.slug,
            title=request.title,
            description=request.description,
            version=request.version,
            initial_visibility=request.initial_visibility,
        )
        return {"status": "success", "data": payload}
    except WebPublishError as error:
        return _error_response(error)


@router.get("/{plugin_id}/status")
async def get_web_publish_status(plugin_id: str, authorization: str | None = Header(default=None)):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    try:
        payload = await get_web_publish_service().get_publish_status(
            plugin_id,
            supabase_access_token=_extract_bearer_token(authorization),
        )
        return {"status": "success", "data": payload}
    except WebPublishError as error:
        return _error_response(error)


@router.get("/{plugin_id}/tasks/{task_id}")
async def get_web_publish_task(plugin_id: str, task_id: str):
    manager = get_plugin_manager()
    if not manager._initialized:
        await manager.initialize()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        return JSONResponse(status_code=404, content={"code": "publish_plugin_not_found", "message": f"Plugin not found: {plugin_id}"})
    try:
        payload = get_web_publish_service().get_publish_task(plugin_id, task_id)
        return {"status": "success", "data": payload}
    except WebPublishError as error:
        return _error_response(error)
