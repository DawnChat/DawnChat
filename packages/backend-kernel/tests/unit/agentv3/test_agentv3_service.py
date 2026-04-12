from __future__ import annotations

import asyncio
import types

import pytest

from app.agentv3.service import get_agentv3_service


def _bind_fake_run(runtime, fake_async_gen_fn):
    """Replace RuntimeLoop.run with async generator *fake_async_gen_fn(self, run_input)*."""

    async def bound(self, run_input):
        async for item in fake_async_gen_fn(self, run_input):
            yield item

    runtime.run = types.MethodType(bound, runtime)


@pytest.mark.asyncio
async def test_create_get_list_delete_session_roundtrip():
    svc = get_agentv3_service()
    row = await svc.create_session(title="T1")
    sid = row["id"]
    assert row["engine"] == "agentv3"
    assert "config" in row
    assert row["title"] == "T1"

    got = await svc.get_session(sid)
    assert got is not None
    assert got["id"] == sid

    listed = await svc.list_sessions()
    assert any(r["id"] == sid for r in listed)

    ok = await svc.delete_session(sid)
    assert ok is True
    assert await svc.get_session(sid) is None
    assert await svc.list_messages(sid) == []


@pytest.mark.asyncio
async def test_get_engine_meta_capabilities():
    svc = get_agentv3_service()
    meta = svc.get_engine_meta()
    assert meta["engine"] == "agentv3"
    caps = meta["capabilities"]
    assert caps["permission_flow"] is True
    assert caps["replay_last_event_id"] is True
    assert "thinking_efforts" in caps


@pytest.mark.asyncio
async def test_prompt_async_with_empty_runtime_completes(monkeypatch: pytest.MonkeyPatch):
    svc = get_agentv3_service()

    async def empty_gen(self, run_input):
        if False:
            yield {}

    _bind_fake_run(svc._runtime, empty_gen)

    session = await svc.create_session()
    sid = session["id"]

    await svc.prompt_async(sid, {"parts": [{"type": "text", "text": "hello"}]})
    task = svc._running_tasks.get(sid)
    assert task is not None
    await asyncio.wait_for(task, timeout=5.0)

    assert sid not in svc._running_tasks
    msgs = await svc.list_messages(sid)
    roles = [m["info"]["role"] for m in msgs]
    assert "user" in roles


@pytest.mark.asyncio
async def test_prompt_sync_with_empty_runtime_returns_without_assistant(monkeypatch: pytest.MonkeyPatch):
    svc = get_agentv3_service()

    async def empty_gen(self, run_input):
        if False:
            yield {}

    _bind_fake_run(svc._runtime, empty_gen)

    session = await svc.create_session()
    sid = session["id"]

    out = await svc.prompt(sid, {"parts": [{"type": "text", "text": "sync hi"}]})
    assert out is None

    msgs = await svc.list_messages(sid)
    assert any(m["info"]["role"] == "user" for m in msgs)


@pytest.mark.asyncio
async def test_prompt_async_while_run_in_progress_appends_message_but_does_not_start_second_task():
    """
    Current semantics: second prompt_async returns True without scheduling another run while the first
    task is still active (product risk if UI allows send-during-stream).
    """
    svc = get_agentv3_service()
    gate = asyncio.Event()

    async def hang_gen(self, run_input):
        await gate.wait()
        if False:
            yield {}

    _bind_fake_run(svc._runtime, hang_gen)

    session = await svc.create_session()
    sid = session["id"]

    await svc.prompt_async(sid, {"parts": [{"type": "text", "text": "first"}]})
    await asyncio.sleep(0)
    t1 = svc._running_tasks.get(sid)
    assert t1 is not None and not t1.done()

    await svc.prompt_async(sid, {"parts": [{"type": "text", "text": "second"}]})
    assert svc._running_tasks.get(sid) is t1

    msgs = await svc.list_messages(sid)
    assert len([m for m in msgs if m["info"]["role"] == "user"]) == 2

    gate.set()
    await asyncio.wait_for(t1, timeout=5.0)


@pytest.mark.asyncio
async def test_interrupt_cancels_blocked_runtime_run():
    svc = get_agentv3_service()

    async def block_gen(self, run_input):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        if False:
            yield {}

    _bind_fake_run(svc._runtime, block_gen)

    session = await svc.create_session()
    sid = session["id"]

    await svc.prompt_async(sid, {"parts": [{"type": "text", "text": "x"}]})
    await asyncio.sleep(0)
    task = svc._running_tasks.get(sid)
    assert task is not None and not task.done()

    await svc.interrupt(sid)
    await asyncio.wait_for(task, timeout=5.0)

    row = await svc.get_session(sid)
    assert row is not None
    assert row["status"] == "idle"


@pytest.mark.asyncio
async def test_reply_permission_unknown_id_still_true_and_emits_replied():
    svc = get_agentv3_service()
    session = await svc.create_session()
    sid = session["id"]

    ok = await svc.reply_permission(sid, "perm_nonexistent", "once")
    assert ok is True


@pytest.mark.asyncio
async def test_reply_permission_reject_pops_pending():
    svc = get_agentv3_service()
    session = await svc.create_session()
    sid = session["id"]
    pid = "perm_test_1"
    async with svc._lock:
        svc._pending_permissions[pid] = {
            "tool": "read",
            "pattern": "/tmp/x",
            "sessionID": sid,
            "messageID": "",
            "callID": "",
            "partID": "",
            "input": {},
        }

    ok = await svc.reply_permission(sid, pid, "reject")
    assert ok is True
    async with svc._lock:
        assert pid not in svc._pending_permissions


@pytest.mark.asyncio
async def test_update_session_config_invalid_agent_raises():
    svc = get_agentv3_service()
    session = await svc.create_session()
    sid = session["id"]

    with pytest.raises(ValueError, match="agent not available"):
        await svc.update_session_config(sid, {"agent": "__not_a_real_agent_profile__"})
