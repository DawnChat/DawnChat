import pytest

from app.storage.manager import StorageManager


class _ConfigStorageStub:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def get(self, key: str, default=None):
        return self.values.get(key, default)

    async def set(self, key: str, value) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> bool:
        existed = key in self.values
        self.values.pop(key, None)
        return existed

    async def get_by_prefix(self, prefix: str) -> dict[str, object]:
        return {k: v for k, v in self.values.items() if k.startswith(prefix)}


class _SecureStorageStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []

    async def get(self, key: str):
        self.get_calls.append(key)
        return self.values.get(key)

    async def set(self, key: str, value: str) -> None:
        self.set_calls.append((key, value))
        self.values[key] = value

    async def delete(self, key: str) -> bool:
        self.delete_calls.append(key)
        return self.values.pop(key, None) is not None


def _build_manager() -> StorageManager:
    manager = StorageManager.__new__(StorageManager)
    manager._initialized = True
    manager._api_key_cache = {}
    manager.config_storage = _ConfigStorageStub()
    manager.secure_storage = _SecureStorageStub()
    return manager


@pytest.mark.asyncio
async def test_provider_marker_read_write_and_list() -> None:
    manager = _build_manager()

    await manager.set_provider_has_key("openai", True)
    await manager.set_provider_has_key("anthropic", False)
    await manager.set_provider_has_key("gemini", True)

    assert await manager.get_provider_has_key("openai") is True
    assert await manager.get_provider_has_key("anthropic") is False
    assert await manager.get_provider_has_key("missing") is False
    assert await manager.list_providers_with_key_marker() == ["gemini", "openai"]


@pytest.mark.asyncio
async def test_get_marked_api_key_skips_keyring_when_marker_false() -> None:
    manager = _build_manager()
    secure_storage = manager.secure_storage

    value = await manager.get_marked_api_key("openai")

    assert value is None
    assert secure_storage.get_calls == []


@pytest.mark.asyncio
async def test_get_marked_api_key_self_heals_marker_when_key_missing() -> None:
    manager = _build_manager()
    secure_storage = manager.secure_storage
    await manager.set_provider_has_key("openai", True)

    value = await manager.get_marked_api_key("openai")

    assert value is None
    assert secure_storage.get_calls == ["openai_api_key"]
    assert await manager.get_provider_has_key("openai") is False


@pytest.mark.asyncio
async def test_get_marked_api_key_uses_cache_after_first_read() -> None:
    manager = _build_manager()
    secure_storage = manager.secure_storage
    secure_storage.values["openai_api_key"] = "sk-openai"
    await manager.set_provider_has_key("openai", True)

    first = await manager.get_marked_api_key("openai")
    second = await manager.get_marked_api_key("openai")

    assert first == "sk-openai"
    assert second == "sk-openai"
    assert secure_storage.get_calls == ["openai_api_key"]


@pytest.mark.asyncio
async def test_set_delete_api_key_updates_marker_and_cache() -> None:
    manager = _build_manager()
    secure_storage = manager.secure_storage

    await manager.set_api_key("openai", "sk-openai")
    assert await manager.get_provider_has_key("openai") is True
    assert secure_storage.set_calls == [("openai_api_key", "sk-openai")]

    await manager.delete_api_key("openai")
    assert await manager.get_provider_has_key("openai") is False
    assert secure_storage.delete_calls == ["openai_api_key"]
