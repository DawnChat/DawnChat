import pytest

from app.voice.azure_tts_service import AzureTtsService


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
