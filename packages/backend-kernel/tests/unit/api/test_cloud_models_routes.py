import pytest

from app.api import cloud_models_routes
from app.storage import storage_manager


@pytest.mark.asyncio
async def test_list_providers_includes_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_api_key(provider_id: str):
        if provider_id == "openrouter":
            return "or-key-123"
        return None

    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)

    payload = await cloud_models_routes.list_providers()
    provider_ids = {item["id"] for item in payload["providers"]}

    assert "openrouter" in provider_ids


@pytest.mark.asyncio
async def test_get_provider_config_api_reads_dynamic_models(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_api_key(_provider_id: str):
        return None

    async def _get_app_config(key: str):
        if key == "provider.openrouter.models":
            return ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]
        return None

    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)

    payload = await cloud_models_routes.get_provider_config_api("openrouter")

    assert payload["provider"]["id"] == "openrouter"
    assert payload["provider"]["models"] == ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]


@pytest.mark.asyncio
async def test_set_provider_enabled_models_allows_models_without_hardcoded_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: dict[str, object] = {}

    async def _get_app_config(key: str):
        if key == "provider.openrouter.models":
            return []
        return None

    async def _set_app_config(key: str, value):
        writes[key] = value

    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "set_app_config", _set_app_config)

    payload = await cloud_models_routes.set_provider_enabled_models(
        "openrouter",
        cloud_models_routes.EnabledModelsRequest(models=["openai/gpt-4.1"]),
    )

    assert payload["status"] == "success"
    assert writes["provider.openrouter.enabled_models"] == ["openai/gpt-4.1"]
