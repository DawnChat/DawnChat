import pytest

from app.storage import storage_manager


@pytest.mark.asyncio
async def test_get_marked_api_key_skips_keyring_when_marker_false(monkeypatch: pytest.MonkeyPatch) -> None:
    storage_manager._api_key_cache.clear()
    get_api_key_called = False

    async def _get_provider_has_key(provider: str) -> bool:
        return False

    async def _get_api_key(provider: str):
        nonlocal get_api_key_called
        get_api_key_called = True
        return "sk-test"

    monkeypatch.setattr(storage_manager, "get_provider_has_key", _get_provider_has_key)
    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)

    value = await storage_manager.get_marked_api_key("openai")
    assert value is None
    assert get_api_key_called is False


@pytest.mark.asyncio
async def test_get_marked_api_key_self_heals_when_marker_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    storage_manager._api_key_cache.clear()
    marker_updates: list[tuple[str, bool]] = []

    async def _get_provider_has_key(provider: str) -> bool:
        return True

    async def _get_api_key(provider: str):
        return None

    async def _set_provider_has_key(provider: str, has_key: bool) -> None:
        marker_updates.append((provider, has_key))

    monkeypatch.setattr(storage_manager, "get_provider_has_key", _get_provider_has_key)
    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)
    monkeypatch.setattr(storage_manager, "set_provider_has_key", _set_provider_has_key)

    value = await storage_manager.get_marked_api_key("openai")
    assert value is None
    assert marker_updates == [("openai", False)]


@pytest.mark.asyncio
async def test_list_providers_with_key_marker_filters_true_values(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_by_prefix(prefix: str):
        return {
            "provider.openai.has_key": True,
            "provider.anthropic.has_key": False,
            "provider.gemini.has_key": True,
            "provider.malformed": True,
        }

    monkeypatch.setattr(storage_manager.config_storage, "get_by_prefix", _get_by_prefix)

    providers = await storage_manager.list_providers_with_key_marker()
    assert providers == ["gemini", "openai"]


@pytest.mark.asyncio
async def test_set_api_key_updates_marker_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    storage_manager._api_key_cache.clear()
    writes: list[tuple[str, str]] = []
    marker_updates: list[tuple[str, bool]] = []

    async def _secure_set(key: str, value: str) -> None:
        writes.append((key, value))

    async def _set_provider_has_key(provider: str, has_key: bool) -> None:
        marker_updates.append((provider, has_key))

    async def _secure_get(key: str):
        raise AssertionError("cache hit expected, should not read secure storage")

    monkeypatch.setattr(storage_manager.secure_storage, "set", _secure_set)
    monkeypatch.setattr(storage_manager.secure_storage, "get", _secure_get)
    monkeypatch.setattr(storage_manager, "set_provider_has_key", _set_provider_has_key)

    await storage_manager.set_api_key("openai", "sk-cached")
    value = await storage_manager.get_api_key("openai")

    assert writes == [("openai_api_key", "sk-cached")]
    assert marker_updates == [("openai", True)]
    assert value == "sk-cached"
