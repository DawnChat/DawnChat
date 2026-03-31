from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.voice import get_tts_artifact_store, get_tts_runtime_service

router = APIRouter(prefix="/tts", tags=["tts"])


class TtsSpeakRequest(BaseModel):
    plugin_id: str
    text: str
    voice: str = ""
    sid: int | None = None
    mode: str = "manual"
    interrupt: bool = False


class TtsStopRequest(BaseModel):
    task_id: str | None = None
    plugin_id: str | None = None


@router.post("/speak")
async def submit_tts_speak(request: TtsSpeakRequest):
    service = get_tts_runtime_service()
    try:
        task_id = await service.submit_speak(
            plugin_id=request.plugin_id,
            text=request.text,
            voice=request.voice,
            sid=request.sid,
            mode=request.mode,
            interrupt=request.interrupt,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {
        "status": "accepted",
        "task_id": task_id,
        "stream_url": f"/api/tts/stream/{task_id}",
        "status_url": f"/api/tts/tasks/{task_id}",
    }


@router.post("/stop")
async def stop_tts_task(request: TtsStopRequest):
    stopped = await get_tts_runtime_service().stop(task_id=request.task_id, plugin_id=request.plugin_id)
    return {"status": "success", "data": {"stopped": bool(stopped)}}


@router.get("/tasks/{task_id}")
async def get_tts_task(task_id: str):
    task = get_tts_runtime_service().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"TTS task not found: {task_id}")
    return {"status": "success", "data": task}


@router.get("/capability")
async def get_tts_capability(plugin_id: str = ""):
    state = get_tts_runtime_service().get_plugin_runtime_state(plugin_id=plugin_id)
    model = state.get("model") if isinstance(state, dict) else {}
    model_payload = model if isinstance(model, dict) else {}
    available = bool(model_payload.get("ready"))
    reason = ""
    if not available:
        reason = str(model_payload.get("error") or "tts_model_not_ready")
    return {
        "status": "success",
        "data": {
            "available": available,
            "engine": "python",
            "reason": reason,
            "model": model_payload,
        },
    }


@router.get("/stream/{task_id}")
async def stream_tts_task(task_id: str, request: Request):
    service = get_tts_runtime_service()
    if service.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail=f"TTS task not found: {task_id}")
    raw_last_event_id = str(request.headers.get("Last-Event-ID") or "").strip()
    parsed_last_event_id: int | None = None
    if raw_last_event_id:
        try:
            parsed_last_event_id = int(raw_last_event_id)
        except ValueError as err:
            raise HTTPException(status_code=400, detail="Invalid Last-Event-ID") from err
        if parsed_last_event_id < 0:
            raise HTTPException(status_code=400, detail="Invalid Last-Event-ID")
    try:
        await service.ensure_event_cursor(task_id, parsed_last_event_id)
    except ValueError as err:
        if str(err) == "tts_event_cursor_not_found":
            raise HTTPException(status_code=409, detail="TTS event cursor not found; please rebuild task state") from err
        raise

    async def event_generator() -> AsyncGenerator[str, None]:
        heartbeat_seconds = 12.0
        yield "retry: 1500\n\n"
        iterator = service.subscribe_events(task_id, last_event_id=parsed_last_event_id)
        while True:
            try:
                payload = await asyncio.wait_for(anext(iterator), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            except StopAsyncIteration:
                break
            event = str(payload.get("event") or "message")
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            event_id = str(payload.get("_id") or "").strip()
            lines = []
            if event_id:
                lines.append(f"id: {event_id}")
            lines.append(f"event: {event}")
            lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
            yield "\n".join(lines) + "\n\n"
        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/audio/{task_id}/{seq}.wav")
async def get_tts_audio(task_id: str, seq: int):
    path = get_tts_artifact_store().resolve_segment(task_id, seq)
    if not path:
        raise HTTPException(status_code=404, detail=f"TTS segment not found: {task_id}/{seq}")
    return FileResponse(path=path, media_type="audio/wav", filename=f"{seq}.wav")
