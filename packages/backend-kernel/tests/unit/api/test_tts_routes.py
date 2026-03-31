import pytest
from starlette.requests import Request

from app.api import tts_routes as routes


class _RuntimeStub:
    def __init__(self) -> None:
        self.tasks = {"task-1": {"task_id": "task-1", "status": "running"}}
        self.last_event_id = None
        self.raise_cursor_not_found = False
        self.model_ready = True
        self.model_error = ""

    async def submit_speak(self, **kwargs):
        return "task-1"

    async def stop(self, **kwargs):
        return True

    def get_task(self, task_id: str):
        return self.tasks.get(task_id)

    def get_plugin_runtime_state(self, plugin_id: str):
        return {
            "model": {
                "ready": self.model_ready,
                "error": self.model_error,
            }
        }

    async def ensure_event_cursor(self, task_id: str, last_event_id: int | None):
        self.last_event_id = last_event_id
        if self.raise_cursor_not_found:
            raise ValueError("tts_event_cursor_not_found")

    async def subscribe_events(self, task_id: str, last_event_id: int | None = None):
        self.last_event_id = last_event_id
        yield {"event": "segment_ready", "data": {"task_id": task_id, "seq": 1, "url": "/api/tts/audio/task-1/1.wav"}, "_id": 1}
        yield {"event": "done", "data": {"task_id": task_id}, "_id": 2}


class _ArtifactStub:
    def __init__(self, path):
        self.path = path

    def resolve_segment(self, task_id: str, seq: int):
        return self.path


def _build_request(headers: dict[str, str] | None = None) -> Request:
    encoded_headers = []
    for key, value in (headers or {}).items():
        encoded_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/tts/stream/task-1",
        "headers": encoded_headers,
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_submit_tts_speak_returns_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: _RuntimeStub())
    payload = routes.TtsSpeakRequest(plugin_id="com.demo", text="hello", sid=6)
    response = await routes.submit_tts_speak(payload)
    assert response["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_get_tts_task_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: _RuntimeStub())
    response = await routes.get_tts_task("task-1")
    assert response["data"]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_get_tts_capability_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    runtime.model_ready = True
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: runtime)
    response = await routes.get_tts_capability("com.demo")
    assert response["data"]["available"] is True
    assert response["data"]["engine"] == "python"
    assert response["data"]["reason"] == ""


@pytest.mark.asyncio
async def test_get_tts_capability_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    runtime.model_ready = False
    runtime.model_error = "tts_model_not_found"
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: runtime)
    response = await routes.get_tts_capability("com.demo")
    assert response["data"]["available"] is False
    assert response["data"]["reason"] == "tts_model_not_found"


@pytest.mark.asyncio
async def test_stream_tts_task_returns_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: _RuntimeStub())
    response = await routes.stream_tts_task("task-1", _build_request())
    assert response.media_type == "text/event-stream"
    chunks = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    payload = "".join(chunks)
    assert "retry: 1500" in payload
    assert "id: 1" in payload
    assert "event: segment_ready" in payload


@pytest.mark.asyncio
async def test_stream_tts_task_passes_last_event_id(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: runtime)
    response = await routes.stream_tts_task("task-1", _build_request({"Last-Event-ID": "1"}))
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    assert runtime.last_event_id == 1


@pytest.mark.asyncio
async def test_stream_tts_task_invalid_last_event_id_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: _RuntimeStub())
    with pytest.raises(routes.HTTPException) as exc_info:
        await routes.stream_tts_task("task-1", _build_request({"Last-Event-ID": "invalid"}))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_stream_tts_task_cursor_not_found_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    runtime.raise_cursor_not_found = True
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: runtime)
    with pytest.raises(routes.HTTPException) as exc_info:
        await routes.stream_tts_task("task-1", _build_request({"Last-Event-ID": "2"}))
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_tts_task_emits_keepalive_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    monkeypatch.setattr(routes, "get_tts_runtime_service", lambda: runtime)
    original_wait_for = routes.asyncio.wait_for
    call_count = {"value": 0}

    async def _wait_for_stub(awaitable, timeout):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise routes.asyncio.TimeoutError()
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(routes.asyncio, "wait_for", _wait_for_stub)
    response = await routes.stream_tts_task("task-1", _build_request())
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk))
    payload = "".join(chunks)
    assert ": keepalive" in payload
