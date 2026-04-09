import pytest

from app.plugins.application.template_application_service import PluginTemplateApplicationService


class _MarketServiceDouble:
    def __init__(self, plugins):
        self._plugins = plugins
        self.calls: list[bool] = []

    async def list_plugins(self, force_refresh: bool = True):
        self.calls.append(force_refresh)
        return self._plugins


class _FailingScaffolder:
    async def scaffold(self, request) -> None:
        request.target_dir.mkdir(parents=True, exist_ok=True)
        (request.target_dir / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("scaffold boom")


class _ScaffolderRegistryDouble:
    def get(self, app_type: str):
        del app_type
        return _FailingScaffolder()


class _SuccessScaffolder:
    async def scaffold(self, request) -> None:
        request.target_dir.mkdir(parents=True, exist_ok=True)
        (request.target_dir / "manifest.json").write_text("{}", encoding="utf-8")


class _SuccessRegistryDouble:
    def get(self, app_type: str):
        del app_type
        return _SuccessScaffolder()


def _build_service(tmp_path):
    target_dir = tmp_path / "com.demo.plugin"

    async def _refresh_registry() -> None:
        return None

    return PluginTemplateApplicationService(
        registry=object(),
        template_scaffolders=_SuccessRegistryDouble(),
        suggest_unique_plugin_id=lambda **_: "com.demo.plugin",
        get_plugin_source_dir=lambda _: target_dir,
        metadata_upsert=lambda *_args, **_kwargs: None,
        refresh_registry=_refresh_registry,
        get_plugin_snapshot=lambda _: None,
        prepare_plugin_runtime=lambda _: None,
    )


@pytest.mark.asyncio
async def test_scaffold_rolls_back_target_dir_when_scaffolder_fails(tmp_path, monkeypatch) -> None:
    template_source = tmp_path / "template-source"
    template_source.mkdir(parents=True, exist_ok=True)
    target_dir = tmp_path / "com.demo.plugin"
    metadata_calls: list[tuple[str, dict]] = []
    refresh_calls: list[bool] = []

    async def _refresh_registry() -> None:
        refresh_calls.append(True)

    service = PluginTemplateApplicationService(
        registry=object(),
        template_scaffolders=_ScaffolderRegistryDouble(),
        suggest_unique_plugin_id=lambda **_: "com.demo.plugin",
        get_plugin_source_dir=lambda _: target_dir,
        metadata_upsert=lambda plugin_id, patch: metadata_calls.append((plugin_id, patch)),
        refresh_registry=_refresh_registry,
        get_plugin_snapshot=lambda _: None,
        prepare_plugin_runtime=lambda _: None,
    )

    async def _fake_ensure_template_cached(template_id: str, *, force_refresh: bool = True):
        del template_id, force_refresh
        return {"source_dir": str(template_source), "version": "1.0.0"}

    monkeypatch.setattr(service, "ensure_template_cached", _fake_ensure_template_cached)

    with pytest.raises(RuntimeError, match="scaffold boom"):
        await service.scaffold_plugin_from_template(
            template_id="com.template",
            app_name="Demo",
            app_description="desc",
            desired_id="demo",
            owner_email="demo@example.com",
            owner_user_id="u1",
            app_type="desktop",
        )

    assert target_dir.exists() is False
    assert metadata_calls == []
    assert refresh_calls == []


@pytest.mark.asyncio
async def test_scaffold_persists_main_assistant_identity_metadata(tmp_path, monkeypatch) -> None:
    template_source = tmp_path / "template-source"
    template_source.mkdir(parents=True, exist_ok=True)
    target_dir = tmp_path / "com.demo.main-assistant"
    metadata_calls: list[tuple[str, dict]] = []
    refresh_calls: list[bool] = []

    async def _refresh_registry() -> None:
        refresh_calls.append(True)

    service = PluginTemplateApplicationService(
        registry=object(),
        template_scaffolders=_SuccessRegistryDouble(),
        suggest_unique_plugin_id=lambda **_: "com.demo.main-assistant",
        get_plugin_source_dir=lambda _: target_dir,
        metadata_upsert=lambda plugin_id, patch: metadata_calls.append((plugin_id, patch)),
        refresh_registry=_refresh_registry,
        get_plugin_snapshot=lambda _: None,
        prepare_plugin_runtime=lambda _: None,
    )

    async def _fake_ensure_template_cached(template_id: str, *, force_refresh: bool = True):
        del template_id, force_refresh
        return {"source_dir": str(template_source), "version": "1.0.0"}

    monkeypatch.setattr(service, "ensure_template_cached", _fake_ensure_template_cached)

    await service.scaffold_plugin_from_template(
        template_id="com.dawnchat.desktop-ai-assistant",
        app_name="Main Assistant",
        app_description="desc",
        desired_id="main-assistant",
        owner_email="demo@example.com",
        owner_user_id="u1",
        app_type="desktop",
        source_type="official_user_main_assistant",
        is_main_assistant=True,
    )

    assert len(metadata_calls) == 1
    plugin_id, metadata = metadata_calls[0]
    assert plugin_id == "com.demo.main-assistant"
    assert metadata["source_type"] == "official_user_main_assistant"
    assert metadata["is_main_assistant"] is True
    assert refresh_calls == [True]


@pytest.mark.asyncio
async def test_ensure_template_cached_prefers_local_template_in_dev_runtime(tmp_path, monkeypatch) -> None:
    service = _build_service(tmp_path)
    local_template = {
        "template_id": "com.dawnchat.desktop-ai-assistant",
        "version": "0.1.0",
        "source_dir": str(tmp_path / "local-template"),
        "source": "bundled",
    }
    market = _MarketServiceDouble(
        [
            {
                "id": "com.dawnchat.desktop-ai-assistant",
                "version": "9.9.9",
                "package": {"url": "https://example.com/template.zip"},
            }
        ]
    )

    monkeypatch.setattr(
        "app.plugins.application.template_application_service.Config.get_runtime_distribution_mode",
        lambda: "dev",
    )
    monkeypatch.setattr(
        service,
        "_resolve_local_template_source",
        lambda template_id: local_template if template_id == local_template["template_id"] else None,
    )
    monkeypatch.setattr(
        "app.plugins.application.template_application_service.get_plugin_market_service",
        lambda: market,
    )

    result = await service.ensure_template_cached("com.dawnchat.desktop-ai-assistant")

    assert result is local_template
    assert market.calls == []
