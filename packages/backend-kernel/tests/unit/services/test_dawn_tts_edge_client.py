import pytest

from app.services.dawn_tts_edge_client import DawnTtsEdgeError, synthesize_to_mp3


@pytest.mark.asyncio
async def test_synthesize_to_mp3_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 200
        content = b"\xff\xfb\x90\x00"
        headers = {"content-type": "audio/mpeg"}

        def json(self):
            return {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.dawn_tts_edge_client.Config.SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr("app.services.dawn_tts_edge_client.httpx.AsyncClient", _Client)
    async def _trust() -> bool:
        return False

    monkeypatch.setattr(
        "app.services.dawn_tts_edge_client.NetworkService.user_proxy_httpx_trust_env",
        _trust,
    )
    monkeypatch.setattr(
        "app.services.dawn_tts_edge_client.WebPublishService._resolve_supabase_apikey",
        lambda: "anon",
    )

    out = await synthesize_to_mp3(access_token="jwt", text="hi", voice="zh-CN-XiaoxiaoNeural")
    assert out.startswith(b"\xff\xfb")


@pytest.mark.asyncio
async def test_synthesize_to_mp3_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 401
        content = b"{}"
        headers = {"content-type": "application/json"}

        def json(self):
            return {"code": "unauthorized"}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("app.services.dawn_tts_edge_client.Config.SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr("app.services.dawn_tts_edge_client.httpx.AsyncClient", _Client)
    async def _trust() -> bool:
        return False

    monkeypatch.setattr(
        "app.services.dawn_tts_edge_client.NetworkService.user_proxy_httpx_trust_env",
        _trust,
    )
    monkeypatch.setattr(
        "app.services.dawn_tts_edge_client.WebPublishService._resolve_supabase_apikey",
        lambda: "anon",
    )

    with pytest.raises(DawnTtsEdgeError) as exc:
        await synthesize_to_mp3(access_token="jwt", text="hi", voice="zh-CN-XiaoxiaoNeural")
    assert exc.value.code == "dawn_tts_unauthorized"
