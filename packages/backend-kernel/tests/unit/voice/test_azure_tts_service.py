import pytest
import httpx

from app.voice.azure_tts_service import AzureTtsResolvedConfig, AzureTtsService


class _StorageStub:
    def __init__(self) -> None:
        self.api_keys: dict[str, str] = {"azure_tts": "k-demo"}
        self.configs: dict[str, str] = {}

    async def get_api_key(self, provider: str):
        return self.api_keys.get(provider)

    async def set_api_key(self, provider: str, api_key: str):
        self.api_keys[provider] = api_key

    async def get_app_config(self, key: str, default=None):
        return self.configs.get(key, default)

    async def set_app_config(self, key: str, value):
        self.configs[key] = value


@pytest.mark.asyncio
async def test_resolve_voice_prefers_explicit_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService()
    storage = _StorageStub()
    monkeypatch.setattr("app.voice.azure_tts_service.storage_manager", storage)
    resolved = await service._resolve_voice(
        voice="en-US-JennyNeural",
        text="你好",
        default_voice_zh="zh-CN-XiaoxiaoNeural",
        default_voice_en="en-US-JennyNeural",
    )
    assert resolved == "en-US-JennyNeural"


@pytest.mark.asyncio
async def test_resolve_voice_uses_language_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService()
    storage = _StorageStub()
    monkeypatch.setattr("app.voice.azure_tts_service.storage_manager", storage)
    resolved_en = await service._resolve_voice(
        voice="",
        text="hello world",
        default_voice_zh="zh-CN-XiaoxiaoNeural",
        default_voice_en="en-US-JennyNeural",
    )
    resolved_zh = await service._resolve_voice(
        voice="",
        text="你好，世界",
        default_voice_zh="zh-CN-XiaoxiaoNeural",
        default_voice_en="en-US-JennyNeural",
    )
    assert resolved_en.startswith("en-")
    assert resolved_zh.startswith("zh-")


def test_build_ssml_uses_voice_locale() -> None:
    payload = AzureTtsService._build_ssml(text="hello", voice="en-US-JennyNeural")
    assert 'xml:lang="en-US"' in payload
    assert 'name="en-US-JennyNeural"' in payload


class _ResponseStub:
    def __init__(self, *, status_code: int = 200, content: bytes = b"RIFFDATA") -> None:
        self.status_code = status_code
        self.content = content


class _ClientStub:
    def __init__(self, handler) -> None:
        self._handler = handler
        self.is_closed = False
        self.post_calls = 0

    async def post(self, *args, **kwargs):
        self.post_calls += 1
        return await self._handler(*args, **kwargs)

    async def aclose(self) -> None:
        self.is_closed = True


def _config() -> AzureTtsResolvedConfig:
    return AzureTtsResolvedConfig(
        api_key="k-demo",
        region="eastus",
        voice="zh-CN-XiaoxiaoNeural",
        default_voice_zh="zh-CN-XiaoxiaoNeural",
        default_voice_en="en-US-JennyNeural",
    )


@pytest.mark.asyncio
async def test_synthesize_once_reuses_service_level_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService(max_attempts=1)
    created_clients: list[_ClientStub] = []

    async def _ok_handler(*args, **kwargs):
        del args, kwargs
        return _ResponseStub()

    def _create_client():
        client = _ClientStub(_ok_handler)
        created_clients.append(client)
        return client

    monkeypatch.setattr(service, "_create_http_client", _create_client)

    result_a = await service._synthesize_once(config=_config(), text="hello")
    result_b = await service._synthesize_once(config=_config(), text="world")
    assert result_a and result_b
    assert len(created_clients) == 1
    assert created_clients[0].post_calls == 2


@pytest.mark.asyncio
async def test_synthesize_once_retries_and_succeeds_after_transient_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AzureTtsService(max_attempts=3, retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.01)
    request = httpx.Request("POST", "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1")
    
    async def _network_error(*args, **kwargs):
        del args, kwargs
        raise httpx.ConnectError("boom", request=request)

    first_client = _ClientStub(_network_error)

    async def _ok_handler(*args, **kwargs):
        del args, kwargs
        return _ResponseStub(content=b"OK")

    second_client = _ClientStub(_ok_handler)
    clients = [first_client, second_client]

    def _create_client():
        return clients.pop(0)

    monkeypatch.setattr(service, "_create_http_client", _create_client)

    output = await service._synthesize_once(config=_config(), text="hello")
    assert output == b"OK"
    assert first_client.post_calls == 1
    assert second_client.post_calls == 1


@pytest.mark.asyncio
async def test_synthesize_once_non_retryable_error_fast_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService(max_attempts=3, retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.01)

    async def _unauthorized(*args, **kwargs):
        del args, kwargs
        return _ResponseStub(status_code=401)

    client = _ClientStub(_unauthorized)
    monkeypatch.setattr(service, "_create_http_client", lambda: client)

    with pytest.raises(ValueError, match="azure_tts_auth_failed"):
        await service._synthesize_once(config=_config(), text="hello")
    assert client.post_calls == 1


@pytest.mark.asyncio
async def test_synthesize_once_retry_exhausted_returns_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService(max_attempts=2, retry_base_delay_seconds=0.01, retry_max_delay_seconds=0.01)
    request = httpx.Request("POST", "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1")

    async def _always_timeout(*args, **kwargs):
        del args, kwargs
        raise httpx.ReadTimeout("timeout", request=request)

    client_a = _ClientStub(_always_timeout)
    client_b = _ClientStub(_always_timeout)
    clients = [client_a, client_b]
    monkeypatch.setattr(service, "_create_http_client", lambda: clients.pop(0))

    with pytest.raises(ValueError, match="azure_tts_timeout"):
        await service._synthesize_once(config=_config(), text="hello")
    assert client_a.post_calls == 2
    assert client_b.post_calls == 0


@pytest.mark.asyncio
async def test_aclose_closes_reused_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    service = AzureTtsService(max_attempts=1)
    client = _ClientStub(lambda *a, **k: _ResponseStub())
    monkeypatch.setattr(service, "_create_http_client", lambda: client)
    await service._get_http_client()
    await service.aclose()
    assert client.is_closed is True
    assert service._http_client is None
