from pathlib import Path

import pytest

from app.services.claude_baseline_config_composer import ClaudeBaselineConfigComposer
from app.storage import storage_manager


class _InstructionResolverStub:
    def resolve_instructions(
        self,
        *,
        workspace: Path | None,
        include_shared_rules: bool,
        include_workspace_rules: bool,
    ) -> list[str]:
        if include_shared_rules and include_workspace_rules and workspace is not None:
            return ["/shared/context/base.md", "AGENTS.md"]
        if include_workspace_rules and workspace is not None:
            return ["AGENTS.md"]
        return ["/shared/context/base.md"]


@pytest.mark.asyncio
async def test_compose_builds_claude_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_api_key(provider_id: str):
        return "sk-test" if provider_id == "anthropic" else None

    async def _get_app_config(key: str):
        if key == "provider.anthropic.enabled_models":
            return ["claude-sonnet-4-20250514"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    composer = ClaudeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(workspace=Path("/tmp/demo"), rules_dir="/tmp/rules")

    assert result.config["model"] == "anthropic/claude-sonnet-4-20250514"
    assert result.config["default_agent"] == "build"
    assert result.config["instructions"] == ["/shared/context/base.md", "AGENTS.md"]
    assert result.config["rules_dir"] == "/tmp/rules"
    assert result.config["providers"]["anthropic"]["configured"] is True


@pytest.mark.asyncio
async def test_compose_respects_instruction_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_api_key(provider_id: str):
        return "sk-test" if provider_id == "anthropic" else None

    async def _get_app_config(key: str):
        if key == "provider.anthropic.enabled_models":
            return ["claude-sonnet-4-20250514"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_api_key", _get_api_key)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    composer = ClaudeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(
        workspace=Path("/tmp/demo"),
        instruction_policy={"include_shared_rules": False, "include_workspace_rules": True},
    )

    assert result.config["instructions"] == ["AGENTS.md"]
