from __future__ import annotations

import asyncio

import pytest

from app.agentv3.event_hub import AgentV3EventHub


@pytest.mark.asyncio
async def test_stamp_event_event_id_monotonic_and_seq_per_session():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_a"

    a = await hub.stamp_event(
        {"type": "session.idle", "sessionID": sid, "messageID": None, "properties": {}},
        lock=lock,
    )
    b = await hub.stamp_event(
        {"type": "session.idle", "sessionID": sid, "messageID": None, "properties": {}},
        lock=lock,
    )
    c = await hub.stamp_event(
        {"type": "server.connected", "sessionID": "", "messageID": None, "properties": {}},
        lock=lock,
    )

    assert a["eventID"] < b["eventID"] < c["eventID"]
    assert a["seq"] == 1
    assert b["seq"] == 2
    assert "seq" not in c


@pytest.mark.asyncio
async def test_transport_events_not_in_history_replayable_others_are():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_hist"

    await hub.stamp_event(
        {"type": "server.connected", "sessionID": "", "messageID": None, "properties": {}},
        lock=lock,
    )
    await hub.stamp_event(
        {"type": "server.heartbeat", "sessionID": "", "messageID": None, "properties": {}},
        lock=lock,
    )
    await hub.stamp_event(
        {"type": "session.idle", "sessionID": sid, "messageID": None, "properties": {}},
        lock=lock,
    )

    assert len(hub.event_history) == 1
    assert hub.event_history[0]["type"] == "session.idle"


@pytest.mark.asyncio
async def test_subscribe_replays_events_after_last_event_id():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_replay"

    first = await hub.stamp_event(
        {
            "type": "message.updated",
            "sessionID": sid,
            "messageID": "m_old",
            "properties": {"info": {"id": "m_old", "role": "user"}},
        },
        lock=lock,
    )
    second = await hub.stamp_event(
        {
            "type": "message.updated",
            "sessionID": sid,
            "messageID": "m_new",
            "properties": {"info": {"id": "m_new", "role": "user"}},
        },
        lock=lock,
    )

    collected: list[dict] = []
    agen = hub.subscribe_events(lock=lock, stream_heartbeat_ms=50, last_event_id=int(first["eventID"]))
    try:
        async for ev in agen:
            collected.append(ev)
            if len(collected) >= 3:
                break
    finally:
        await agen.aclose()

    assert collected[0]["type"] == "server.connected"
    assert collected[1]["eventID"] == second["eventID"]
    assert collected[1]["messageID"] == "m_new"
    assert collected[2]["type"] == "server.heartbeat"


@pytest.mark.asyncio
async def test_apply_event_to_store_unknown_session_noop():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sessions: dict = {}
    messages: dict = {}

    await hub.apply_event_to_store(
        {
            "type": "message.updated",
            "sessionID": "missing",
            "messageID": "x",
            "properties": {"info": {"id": "x", "role": "user"}},
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=lambda: "t",
    )

    assert sessions == {}
    assert messages == {}


@pytest.mark.asyncio
async def test_apply_event_to_store_message_and_part_delta():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_msg"
    sessions = {sid: {"status": "running", "time": {"updated": "t0"}}}
    messages: dict[str, list] = {sid: []}

    def now_iso():
        return "t1"

    await hub.apply_event_to_store(
        {
            "type": "message.updated",
            "sessionID": sid,
            "messageID": "m1",
            "properties": {"info": {"id": "m1", "role": "user", "sessionID": sid}},
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=now_iso,
    )
    assert len(messages[sid]) == 1
    assert messages[sid][0]["info"]["role"] == "user"

    await hub.apply_event_to_store(
        {
            "type": "message.part.delta",
            "sessionID": sid,
            "messageID": "",
            "properties": {
                "messageID": "m1",
                "partID": "p1",
                "field": "text",
                "delta": "hel",
                "partType": "text",
            },
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=now_iso,
    )
    parts = messages[sid][0].setdefault("parts", [])
    assert any(p.get("id") == "p1" and p.get("text") == "hel" for p in parts)

    await hub.apply_event_to_store(
        {
            "type": "message.part.delta",
            "sessionID": sid,
            "messageID": "",
            "properties": {
                "messageID": "m1",
                "partID": "p1",
                "field": "text",
                "delta": "lo",
                "partType": "text",
            },
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=now_iso,
    )
    parts = messages[sid][0]["parts"]
    p1 = next(p for p in parts if p.get("id") == "p1")
    assert p1.get("text") == "hello"


@pytest.mark.asyncio
async def test_apply_event_to_store_session_status_updates_row():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_st"
    sessions = {sid: {"status": "idle", "time": {"updated": "t0"}}}
    messages: dict[str, list] = {}

    await hub.apply_event_to_store(
        {
            "type": "session.status",
            "sessionID": sid,
            "messageID": None,
            "properties": {"status": {"type": "busy"}},
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=lambda: "t1",
    )
    assert sessions[sid]["status"] == "running"

    await hub.apply_event_to_store(
        {
            "type": "session.idle",
            "sessionID": sid,
            "messageID": None,
            "properties": {},
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=lambda: "t2",
    )
    assert sessions[sid]["status"] == "idle"


@pytest.mark.asyncio
async def test_apply_event_to_store_message_part_updated_merges():
    hub = AgentV3EventHub()
    lock = asyncio.Lock()
    sid = "ses_part"
    sessions = {sid: {"status": "running", "time": {"updated": "t0"}}}
    messages: dict[str, list] = {sid: [{"info": {"id": "ma", "role": "assistant"}, "parts": []}]}

    await hub.apply_event_to_store(
        {
            "type": "message.part.updated",
            "sessionID": sid,
            "messageID": "",
            "properties": {
                "part": {"id": "tp", "type": "text", "messageID": "ma", "text": "hi"},
            },
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=lambda: "t1",
    )
    assert messages[sid][0]["parts"][0]["text"] == "hi"

    await hub.apply_event_to_store(
        {
            "type": "message.part.updated",
            "sessionID": sid,
            "messageID": "",
            "properties": {
                "part": {"id": "tp", "type": "text", "messageID": "ma", "text": "hello"},
            },
        },
        lock=lock,
        sessions=sessions,
        messages=messages,
        now_iso=lambda: "t2",
    )
    assert messages[sid][0]["parts"][0]["text"] == "hello"
