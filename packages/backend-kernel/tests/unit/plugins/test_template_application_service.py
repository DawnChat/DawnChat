import pytest

from app.plugins.application.template_application_service import PluginTemplateApplicationService


class _FailingScaffolder:
    async def scaffold(self, request) -> None:
        request.target_dir.mkdir(parents=True, exist_ok=True)
        (request.target_dir / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("scaffold boom")


class _ScaffolderRegistryDouble:
    def get(self, app_type: str):
        del app_type
        return _FailingScaffolder()


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
