from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agentv3.service import get_agentv3_service
from app.agentv3.sse_codec import encode_sse_event

router = APIRouter(prefix="/agentv3", tags=["agentv3"])


class SessionCreateRequest(BaseModel):
    title: Optional[str] = None
    workspace_path: Optional[str] = None
    plugin_id: Optional[str] = None
    project_id: Optional[str] = None
    workspace_kind: Optional[str] = None


class SessionPatchRequest(BaseModel):
    title: Optional[str] = None


class SessionConfigPatchRequest(BaseModel):
    agent: Optional[str] = None
    model: Optional[Any] = None
    thinking: Optional[Dict[str, Any]] = None
    max_steps: Optional[int] = None
    permission_rules: Optional[list[Dict[str, Any]]] = None
    permission_default_action: Optional[str] = None
    opencode: Optional[Dict[str, Any]] = None


class PromptRequest(BaseModel):
    parts: list[dict[str, Any]] = Field(default_factory=list)
    agent: Optional[str] = None
    model: Optional[Dict[str, Any]] = None
    system: Optional[str] = None
    noReply: Optional[bool] = None
    plugin_id: Optional[str] = None
    project_id: Optional[str] = None
    workspace_path: Optional[str] = None
    workspace_kind: Optional[str] = None


class PermissionReplyRequest(BaseModel):
    response: Literal["once", "always", "reject"]
    remember: Optional[bool] = None


class ResumeRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


@router.get("/session")
async def list_sessions():
    return await get_agentv3_service().list_sessions()


@router.get("/agents")
async def list_agents():
    return get_agentv3_service().list_agents()


@router.get("/models")
async def list_models():
    return await get_agentv3_service().list_models()


@router.post("/session")
async def create_session(request: SessionCreateRequest):
    try:
        return await get_agentv3_service().create_session(
            title=request.title,
            workspace_path=request.workspace_path,
            plugin_id=request.plugin_id,
            project_id=request.project_id,
            workspace_kind=request.workspace_kind,
        )
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "session_create_failed",
                "message": str(err),
            },
        ) from err


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    row = await get_agentv3_service().get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return row


@router.patch("/session/{session_id}")
async def update_session(session_id: str, patch: SessionPatchRequest):
    row = await get_agentv3_service().update_session(session_id, patch.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return row


@router.patch("/session/{session_id}/config")
async def update_session_config(session_id: str, patch: SessionConfigPatchRequest):
    try:
        row = await get_agentv3_service().update_session_config(session_id, patch.model_dump(exclude_none=True))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not row:
        raise HTTPException(status_code=404, detail="session not found")
    return row


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    ok = await get_agentv3_service().delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return True


@router.get("/session/{session_id}/message")
async def list_messages(session_id: str):
    return await get_agentv3_service().list_messages(session_id)


@router.post("/session/{session_id}/message")
async def prompt_sync(session_id: str, payload: PromptRequest):
    msg = await get_agentv3_service().prompt(session_id, payload.model_dump())
    if not msg:
        raise HTTPException(status_code=404, detail="session not found")
    return msg


@router.post("/session/{session_id}/prompt_async")
async def prompt_async(session_id: str, payload: PromptRequest):
    ok = await get_agentv3_service().prompt_async(session_id, payload.model_dump())
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return True


@router.post("/session/{session_id}/permissions/{permission_id}")
async def reply_permission(session_id: str, permission_id: str, request: PermissionReplyRequest):
    return await get_agentv3_service().reply_permission(
        session_id=session_id,
        permission_id=permission_id,
        response=request.response,
        remember=request.remember,
    )


@router.get("/event")
async def subscribe_events(request: Request):
    service = get_agentv3_service()
    header_value = request.headers.get("last-event-id")
    last_event_id: Optional[int] = None
    if header_value:
        try:
            last_event_id = int(str(header_value).strip())
        except Exception:
            last_event_id = None

    async def stream() -> AsyncIterator[str]:
        async for event in service.subscribe_events(last_event_id=last_event_id):
            yield encode_sse_event(event, retry_ms=1000)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/engine/meta")
async def get_engine_meta():
    return get_agentv3_service().get_engine_meta()


@router.post("/session/{session_id}/interrupt")
async def interrupt(session_id: str):
    return await get_agentv3_service().interrupt(session_id)


@router.post("/session/{session_id}/resume")
async def resume(session_id: str, request: ResumeRequest):
    return await get_agentv3_service().resume(session_id, request.payload)

