import pytest

from app.bootstrap import lifecycle


class _LifecycleManagerStub:
    async def shutdown(self):
        return None


class _LlamaManagerStub:
    async def stop(self, force: bool = False):
        return None


class _MlxInnerStub:
    async def stop(self, force: bool = False):
        return None


class _MlxManagerStub:
    def __init__(self):
        self.lm = _MlxInnerStub()
        self.vlm = _MlxInnerStub()


class _PluginManagerStub:
    async def shutdown(self):
        return None


class _AzureTtsStub:
    async def aclose(self):
        return None


class _OpenCodeManagerStub:
    def __init__(self):
        self.stop_called = False

    async def stop(self):
        self.stop_called = True
        return True


@pytest.mark.asyncio
async def test_shutdown_components_stops_opencode(monkeypatch: pytest.MonkeyPatch):
    opencode_manager = _OpenCodeManagerStub()

    monkeypatch.setattr(lifecycle, "get_lifecycle_manager", lambda: _LifecycleManagerStub())
    monkeypatch.setattr(lifecycle, "get_plugin_manager", lambda: _PluginManagerStub())
    monkeypatch.setattr(lifecycle, "get_azure_tts_service", lambda: _AzureTtsStub())
    monkeypatch.setattr(lifecycle, "get_opencode_manager", lambda: opencode_manager)
    monkeypatch.setattr("app.services.llama_server_manager.get_server_manager", lambda: _LlamaManagerStub())
    monkeypatch.setattr(
        "app.services.mlx_server_manager.get_mlx_server_manager",
        lambda: _MlxManagerStub(),
    )
    monkeypatch.setattr(lifecycle.storage_manager, "close", lambda: None)

    await lifecycle.shutdown_components()

    assert opencode_manager.stop_called is True
