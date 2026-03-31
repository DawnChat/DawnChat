import pytest

from app.services.claude_manager import ClaudeManager, ClaudeUnavailableError
from app.storage import storage_manager


@pytest.mark.asyncio
async def test_patch_config_requires_runtime_ready() -> None:
    manager = ClaudeManager()
    with pytest.raises(ClaudeUnavailableError):
        await manager.patch_config({"model": "anthropic/claude-sonnet-4-20250514"})


@pytest.mark.asyncio
async def test_get_config_providers_marks_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_api_key(provider_id: str):
        return "sk-test" if provider_id == "anthropic" else None

    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)

    manager = ClaudeManager()
    payload = await manager.get_config_providers()
    providers = payload["providers"]
    anthropic = next(item for item in providers if item["id"] == "anthropic")

    assert anthropic["configured"] is True
    assert anthropic["available"] is True


@pytest.mark.asyncio
async def test_patch_config_updates_runtime_config(tmp_path) -> None:
    manager = ClaudeManager()
    manager._runtime_config = {
        "model": "anthropic/claude-3-5-sonnet-20241022",
        "default_agent": "build",
        "providers": {},
    }
    manager._runtime_config_path = tmp_path / "runtime.json"

    result = await manager.patch_config({"model": "anthropic/claude-sonnet-4-20250514"})

    assert result["updated"] is True
    assert manager._runtime_config["model"] == "anthropic/claude-sonnet-4-20250514"


def test_resolve_claude_command_returns_none_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.claude_manager.shutil.which", lambda *_args, **_kwargs: None)
    manager = ClaudeManager()
    assert manager._resolve_claude_command() is None


@pytest.mark.asyncio
async def test_health_payload_marks_unavailable_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.claude_manager.shutil.which", lambda *_args, **_kwargs: None)
    manager = ClaudeManager()

    payload = await manager.get_health_payload()

    assert payload["state"] == "unavailable"
    assert payload["cli_available"] is False
