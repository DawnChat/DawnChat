from pathlib import Path

import pytest

from app.services.opencode_baseline_config_composer import OpenCodeBaselineConfigComposer
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
async def test_compose_builds_baseline_with_resolved_instructions(monkeypatch) -> None:
    async def _get_marked_api_key(provider_id: str):
        return "sk-test" if provider_id == "openai" else None
    async def _list_providers_with_key_marker():
        return ["openai"]

    async def _get_app_config(key: str):
        if key == "provider.openai.enabled_models":
            return ["gpt-4o-mini"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_marked_api_key", _get_marked_api_key)
    monkeypatch.setattr(storage_manager, "list_providers_with_key_marker", _list_providers_with_key_marker)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    import app.services.opencode_baseline_config_composer as composer_module

    monkeypatch.setattr(composer_module.Config, "OPENCODE_INCLUDE_WORKSPACE_RULES", True)
    monkeypatch.setattr(composer_module.Config, "MCP_PROXY_TIMEOUT_READ_SECONDS", 12.0)
    monkeypatch.setattr(composer_module.Config, "OPENCODE_UI_BRIDGE_MCP_TIMEOUT_READ_SECONDS", 310.0)

    composer = OpenCodeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(host="127.0.0.1", port=4096, workspace=Path("/tmp/demo"))

    assert result.config["model"] == "openai/gpt-4o-mini"
    assert result.config["instructions"] == ["/shared/context/base.md", "AGENTS.md"]
    assert "openai" in result.config["provider"]
    assert result.config["provider"]["openai"]["options"]["apiKey"] == "sk-test"
    assert "models" not in result.config["provider"]["openai"]
    assert "dawnchat_ui_bridge" in result.config["mcp"]
    assert "dawnchat_iwp" in result.config["mcp"]
    assert result.config["mcp"]["dawnchat_ui_bridge"]["timeout"] == 310000
    assert result.config["server"]["hostname"] == "127.0.0.1"
    assert result.config["server"]["port"] == 4096


@pytest.mark.asyncio
async def test_compose_can_disable_shared_instructions(monkeypatch) -> None:
    async def _get_marked_api_key(provider_id: str):
        return "sk-test" if provider_id == "openai" else None
    async def _list_providers_with_key_marker():
        return ["openai"]

    async def _get_app_config(key: str):
        if key == "provider.openai.enabled_models":
            return ["gpt-4o-mini"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_marked_api_key", _get_marked_api_key)
    monkeypatch.setattr(storage_manager, "list_providers_with_key_marker", _list_providers_with_key_marker)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    import app.services.opencode_baseline_config_composer as composer_module

    monkeypatch.setattr(composer_module.Config, "OPENCODE_INCLUDE_WORKSPACE_RULES", True)

    composer = OpenCodeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(
        host="127.0.0.1",
        port=4096,
        workspace=Path("/tmp/demo"),
        instruction_policy={"include_shared_rules": False, "include_workspace_rules": True},
    )

    assert result.config["instructions"] == ["AGENTS.md"]


@pytest.mark.asyncio
async def test_compose_injects_plugin_backend_mcp_for_plugin_workspace(monkeypatch) -> None:
    async def _get_marked_api_key(provider_id: str):
        return "sk-test" if provider_id == "openai" else None
    async def _list_providers_with_key_marker():
        return ["openai"]

    async def _get_app_config(key: str):
        if key == "provider.openai.enabled_models":
            return ["gpt-4o-mini"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_marked_api_key", _get_marked_api_key)
    monkeypatch.setattr(storage_manager, "list_providers_with_key_marker", _list_providers_with_key_marker)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    import app.services.opencode_baseline_config_composer as composer_module

    monkeypatch.setattr(composer_module.Config, "OPENCODE_INCLUDE_WORKSPACE_RULES", True)
    monkeypatch.setattr(composer_module.Config, "API_PORT", 7777)
    monkeypatch.setattr(composer_module.Config, "MCP_PROXY_TIMEOUT_READ_SECONDS", 12.0)
    monkeypatch.setattr(composer_module.Config, "OPENCODE_UI_BRIDGE_MCP_TIMEOUT_READ_SECONDS", 310.0)

    composer = OpenCodeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(
        host="127.0.0.1",
        port=4096,
        workspace=Path("/tmp/demo"),
        startup_context={"workspace_kind": "plugin-dev", "plugin_id": "com.demo.plugin"},
    )

    injected = result.config["mcp"]["dawnchat_plugin_backend"]
    assert injected["type"] == "remote"
    assert injected["enabled"] is True
    assert injected["oauth"] is False
    assert injected["timeout"] == 12000
    assert injected["url"] == "http://127.0.0.1:7777/api/opencode/mcp/plugin/com.demo.plugin/backend"
    python_injected = result.config["mcp"]["dawnchat_plugin_python"]
    assert python_injected["type"] == "remote"
    assert python_injected["enabled"] is True
    assert python_injected["oauth"] is False
    assert python_injected["timeout"] == 12000
    assert python_injected["url"] == "http://127.0.0.1:7777/api/opencode/mcp/plugin/com.demo.plugin/python"


@pytest.mark.asyncio
async def test_compose_injects_plugin_mcp_by_default_without_plugin_context(monkeypatch) -> None:
    async def _get_marked_api_key(provider_id: str):
        return "sk-test" if provider_id == "openai" else None
    async def _list_providers_with_key_marker():
        return ["openai"]

    async def _get_app_config(key: str):
        if key == "provider.openai.enabled_models":
            return ["gpt-4o-mini"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_marked_api_key", _get_marked_api_key)
    monkeypatch.setattr(storage_manager, "list_providers_with_key_marker", _list_providers_with_key_marker)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    import app.services.opencode_baseline_config_composer as composer_module

    monkeypatch.setattr(composer_module.Config, "OPENCODE_INCLUDE_WORKSPACE_RULES", True)
    monkeypatch.setattr(composer_module.Config, "API_PORT", 7777)

    composer = OpenCodeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(host="127.0.0.1", port=4096, workspace=Path("/tmp/demo"))

    injected = result.config["mcp"]["dawnchat_plugin_backend"]
    assert injected["url"] == "http://127.0.0.1:7777/api/opencode/mcp/plugin/__default_plugin__/backend"
    assert injected["headers"]["X-DawnChat-Plugin-ID"] == "__default_plugin__"
    python_injected = result.config["mcp"]["dawnchat_plugin_python"]
    assert python_injected["url"] == "http://127.0.0.1:7777/api/opencode/mcp/plugin/__default_plugin__/python"
    assert python_injected["headers"]["X-DawnChat-Plugin-ID"] == "__default_plugin__"


@pytest.mark.asyncio
async def test_compose_skips_unmarked_providers(monkeypatch) -> None:
    read_candidates: list[str] = []

    async def _get_marked_api_key(provider_id: str):
        read_candidates.append(provider_id)
        if provider_id == "openai":
            return "sk-test"
        return None

    async def _list_providers_with_key_marker():
        return ["openai"]

    async def _get_app_config(key: str):
        if key == "provider.openai.enabled_models":
            return ["gpt-4o-mini"]
        return None

    async def _get_config(key: str):
        return None

    monkeypatch.setattr(storage_manager, "get_marked_api_key", _get_marked_api_key)
    monkeypatch.setattr(storage_manager, "list_providers_with_key_marker", _list_providers_with_key_marker)
    monkeypatch.setattr(storage_manager, "get_app_config", _get_app_config)
    monkeypatch.setattr(storage_manager, "get_config", _get_config)

    composer = OpenCodeBaselineConfigComposer(_InstructionResolverStub())
    result = await composer.compose(host="127.0.0.1", port=4096, workspace=Path("/tmp/demo"))

    assert "openai" in result.config["provider"]
    assert read_candidates == ["openai"]
