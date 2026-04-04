import asyncio
from datetime import datetime, timedelta
import time

import pytest

from app.voice.artifact_store import TtsArtifactStore
from app.voice.runtime_service import TtsRuntimeService
from app.voice.synthesis_service import TtsSegment


class _SynthesisStub:
    def __init__(self) -> None:
        self.last_sid = None

    def model_descriptor(self):
        return {"engine": "stub"}

    def split_sentences(self, text: str):
        return [text]

    def synthesize(self, text: str, voice: str = "", sid=None):
        self.last_sid = sid
        return [
            TtsSegment(seq=1, text=text, wav_bytes=b"RIFF", sample_rate=24000, duration_ms=500),
        ]


class _StreamingFailureSynthesisStub:
    def model_descriptor(self):
        return {"engine": "stub"}

    def split_sentences(self, text: str):
        return ["a", "b"]

    def iter_synthesize(self, text: str, voice: str = "", sid=None):
        yield TtsSegment(seq=1, text="a", wav_bytes=b"RIFF", sample_rate=24000, duration_ms=200)
        raise RuntimeError("streaming failed")


class _SlowStreamingSynthesisStub:
    def model_descriptor(self):
        return {"engine": "stub"}

    def split_sentences(self, text: str):
        return ["a", "b"]

    def iter_synthesize(self, text: str, voice: str = "", sid=None):
        time.sleep(0.03)
        yield TtsSegment(seq=1, text="a", wav_bytes=b"RIFF", sample_rate=24000, duration_ms=200)
        time.sleep(0.03)
        yield TtsSegment(seq=2, text="b", wav_bytes=b"RIFF", sample_rate=24000, duration_ms=200)


class _ManySegmentsSynthesisStub:
    def model_descriptor(self):
        return {"engine": "stub"}

    def split_sentences(self, text: str):
        return [f"s-{index}" for index in range(20)]

    def iter_synthesize(self, text: str, voice: str = "", sid=None):
        for index in range(1, 21):
            yield TtsSegment(seq=index, text=f"s-{index}", wav_bytes=b"RIFF", sample_rate=24000, duration_ms=100)


class _AzureStub:
    async def synthesize_segment(self, *, text: str, voice: str = "", sid: int | None = None):
        del text, voice, sid
        return b"RIFF" + (b"\x00" * 96), 24000


@pytest.mark.asyncio
async def test_submit_speak_creates_task(tmp_path) -> None:
    synthesis = _SynthesisStub()
    service = TtsRuntimeService(
        synthesis_service=synthesis,
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello", sid=6)
    assert task_id
    await asyncio.sleep(0.01)
    status = service.get_task(task_id)
    assert status is not None
    assert status["sid"] == 6
    assert synthesis.last_sid == 6


@pytest.mark.asyncio
async def test_stop_by_plugin(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    await service.submit_speak(plugin_id="com.demo", text="hello")
    stopped = await service.stop(plugin_id="com.demo")
    assert stopped is True


@pytest.mark.asyncio
async def test_subscribe_events_replays_history(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    events = []
    async for event in service.subscribe_events(task_id):
        events.append(event)
    assert any(item.get("event") == "segment_ready" for item in events)
    assert any(item.get("event") == "done" for item in events)


@pytest.mark.asyncio
async def test_streaming_publishes_ready_segment_before_error(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_StreamingFailureSynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    events = []
    async for event in service.subscribe_events(task_id):
        events.append(event)
    assert any(item.get("event") == "segment_ready" for item in events)
    assert any(item.get("event") == "error" for item in events)
    status = service.get_task(task_id)
    assert status is not None
    assert status["completed_segments"] == 1


@pytest.mark.asyncio
async def test_subscribe_events_receives_first_segment_before_done(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SlowStreamingSynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    collected = []
    async for event in service.subscribe_events(task_id):
        collected.append(str(event.get("event") or ""))
        if event.get("event") == "segment_ready":
            break
    assert "segment_ready" in collected
    assert "done" not in collected


@pytest.mark.asyncio
async def test_prune_removes_expired_terminal_task_metadata(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
        event_history_ttl_seconds=10,
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    task = service._tasks[task_id]
    task.completed_at = datetime.utcnow() - timedelta(seconds=120)
    async with service._lock:
        service._prune_task_metadata_locked()
    assert service.get_task(task_id) is None


@pytest.mark.asyncio
async def test_subscribe_events_replays_from_last_event_id(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    history = list(service._event_history.get(task_id, []))
    assert len(history) >= 2
    cursor = int(history[0].get("_id") or 0)
    events = []
    async for event in service.subscribe_events(task_id, last_event_id=cursor):
        events.append(event)
    assert events
    assert all(int(item.get("_id") or 0) > cursor for item in events)


@pytest.mark.asyncio
async def test_ensure_event_cursor_raises_when_cursor_not_found(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    with pytest.raises(ValueError, match="tts_event_cursor_not_found"):
        await service.ensure_event_cursor(task_id, 999)


@pytest.mark.asyncio
async def test_publish_drops_slow_watcher_on_backpressure(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
        watcher_queue_maxsize=1,
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=1)
    async with service._lock:
        service._watchers[task_id].append(queue)
    await asyncio.sleep(0.05)
    async with service._lock:
        assert queue not in service._watchers.get(task_id, [])


@pytest.mark.asyncio
async def test_event_history_is_capped_by_max_size(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_ManySegmentsSynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
        max_event_history_per_task=32,
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello")
    await asyncio.sleep(0.05)
    history = list(service._event_history.get(task_id, []))
    assert len(history) == 32


@pytest.mark.asyncio
async def test_record_bridge_notify_updates_runtime_state(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
    )
    await service.record_bridge_notify(plugin_id="com.demo", ok=True)
    await service.record_bridge_notify(plugin_id="com.demo", ok=False, error_code="bridge_not_connected")
    state = service.get_plugin_runtime_state("com.demo")
    bridge = state.get("bridge") or {}
    assert bridge["bridge_notify_total"] == 2
    assert bridge["bridge_notify_failures"] == 1
    assert bridge["last_bridge_error_code"] == "bridge_not_connected"
    assert bridge["last_bridge_error_at"]


def test_map_error_code_refines_runtime_categories() -> None:
    assert TtsRuntimeService._map_error_code("text is required") == "TTS_TEXT_INVALID"
    assert TtsRuntimeService._map_error_code("sherpa-onnx returned empty audio") == "TTS_AUDIO_INVALID"
    assert TtsRuntimeService._map_error_code("task cancelled") == "TTS_RUNTIME_CANCELLED"
    assert TtsRuntimeService._map_error_code("azure_tts_auth_failed") == "TTS_AZURE_FAILED"
    assert TtsRuntimeService._map_error_code("azure_tts_timeout") == "TTS_AZURE_FAILED"
    assert TtsRuntimeService._map_error_code("azure_tts_http_5xx") == "TTS_AZURE_FAILED"


def test_normalize_error_message_handles_blank_exception() -> None:
    class _BlankError(Exception):
        def __str__(self) -> str:
            return ""

    normalized = TtsRuntimeService._normalize_error_message(_BlankError())
    assert normalized == "_BlankError()"


@pytest.mark.asyncio
async def test_submit_speak_azure_engine_generates_segment(tmp_path) -> None:
    service = TtsRuntimeService(
        synthesis_service=_SynthesisStub(),
        artifact_store=TtsArtifactStore(base_dir=tmp_path / "tts"),
        azure_tts_service=_AzureStub(),
    )
    task_id = await service.submit_speak(plugin_id="com.demo", text="hello", engine="azure")
    await asyncio.sleep(0.05)
    status = service.get_task(task_id)
    assert status is not None
    assert status["engine"] == "azure"
    assert status["completed_segments"] == 1
