import pytest

from app.api import opencode_voice_mcp_routes as routes


class _VoiceServiceStub:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {"ok": True, "data": {"task_id": "t-1"}}

    def tool_definitions(self):
        return [
            type(
                "Def",
                (),
                {
                    "name": "dawnchat.voice.speak",
                    "description": "speak",
                    "input_schema": {"type": "object"},
                },
            )()
        ]

    async def execute(self, name: str, arguments: dict):
        return self.payload


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_mcp_voice(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-voice-mcp"


@pytest.mark.asyncio
async def test_tools_list_returns_voice_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_voice_mcp_service", lambda: _VoiceServiceStub())
    body = routes.JsonRpcRequest(id=1, method="tools/list")
    response = await routes.opencode_mcp_voice(body)
    assert response["result"]["tools"][0]["name"] == "dawnchat.voice.speak"


@pytest.mark.asyncio
async def test_tools_call_wraps_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_voice_mcp_service", lambda: _VoiceServiceStub())
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.voice.speak", "arguments": {}})
    response = await routes.opencode_mcp_voice(body)
    assert response["result"]["isError"] is False


@pytest.mark.asyncio
async def test_tools_call_failure_returns_jsonrpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_voice_mcp_service",
        lambda: _VoiceServiceStub(payload={"ok": False, "error_code": "voice_bridge_unavailable", "message": "bridge off"}),
    )
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.voice.speak", "arguments": {}})
    response = await routes.opencode_mcp_voice(body)
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["error_code"] == "voice_bridge_unavailable"
