import pytest

from app.plugins.manager import PluginManager


class _TemplateServiceDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def ensure_template_cached(self, template_id: str, *, force_refresh: bool = True):
        self.calls.append(("ensure_template_cached", (template_id,), {"force_refresh": force_refresh}))
        return {"template_id": template_id}

    async def create_plugin_from_template(self, **kwargs):
        self.calls.append(("create_plugin_from_template", (), kwargs))
        return {"plugin_id": "com.demo.created"}

    async def scaffold_plugin_from_template(self, **kwargs):
        self.calls.append(("scaffold_plugin_from_template", (), kwargs))
        return {"plugin_id": "com.demo.scaffolded"}


class _WebVersionServiceDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def get_web_plugin_versions(self, plugin_id: str):
        self.calls.append(("get_web_plugin_versions", (plugin_id,), {}))
        return {"plugin_id": plugin_id}

    def sync_web_plugin_versions(self, plugin_id: str, version: str):
        self.calls.append(("sync_web_plugin_versions", (plugin_id, version), {}))
        return {"plugin_id": plugin_id, "version": version}


class _MetadataRepositoryDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def upsert(self, plugin_id: str, patch: dict):
        self.calls.append(("upsert", (plugin_id, patch), {}))

    def remove(self, plugin_id: str):
        self.calls.append(("remove", (plugin_id,), {}))

    def update_publish(self, plugin_id: str, patch: dict):
        self.calls.append(("update_publish", (plugin_id, patch), {}))

    def get_publish(self, plugin_id: str):
        self.calls.append(("get_publish", (plugin_id,), {}))
        return {"channel": "web"}

    def update_mobile_publish(self, plugin_id: str, patch: dict):
        self.calls.append(("update_mobile_publish", (plugin_id, patch), {}))

    def get_mobile_publish(self, plugin_id: str):
        self.calls.append(("get_mobile_publish", (plugin_id,), {}))
        return {"channel": "mobile"}

    def all(self):
        self.calls.append(("all", (), {}))
        return {}


@pytest.mark.asyncio
async def test_manager_delegates_template_and_web_version_services() -> None:
    manager = object.__new__(PluginManager)
    manager._template_service = _TemplateServiceDouble()
    manager._web_version_service = _WebVersionServiceDouble()

    ensured = await PluginManager.ensure_template_cached(manager, "com.template", force_refresh=False)
    created = await PluginManager.create_plugin_from_template(
        manager,
        template_id="com.template",
        app_name="Demo",
        app_description="desc",
        desired_id="demo",
        owner_email="demo@example.com",
        owner_user_id="u1",
        app_type="web",
    )
    scaffolded = await PluginManager.scaffold_plugin_from_template(
        manager,
        template_id="com.template",
        app_name="Demo",
        app_description="desc",
        desired_id="demo",
        owner_email="demo@example.com",
        owner_user_id="u1",
        app_type="web",
    )
    versions = PluginManager.get_web_plugin_versions(manager, "com.demo.web")
    synced = PluginManager.sync_web_plugin_versions(manager, "com.demo.web", "1.2.3")

    assert ensured == {"template_id": "com.template"}
    assert created == {"plugin_id": "com.demo.created"}
    assert scaffolded == {"plugin_id": "com.demo.scaffolded"}
    assert versions == {"plugin_id": "com.demo.web"}
    assert synced == {"plugin_id": "com.demo.web", "version": "1.2.3"}


def test_manager_delegates_metadata_repository_methods() -> None:
    manager = object.__new__(PluginManager)
    manager._metadata_repository = _MetadataRepositoryDouble()

    PluginManager._upsert_plugin_metadata(manager, "com.demo", {"k": "v"})
    PluginManager._remove_plugin_metadata(manager, "com.demo")
    PluginManager.update_plugin_publish_metadata(manager, "com.demo", {"last_version": "1.0.0"})
    web_meta = PluginManager.get_plugin_publish_metadata(manager, "com.demo")
    PluginManager.update_plugin_mobile_publish_metadata(manager, "com.demo", {"last_version": "1.0.0"})
    mobile_meta = PluginManager.get_plugin_mobile_publish_metadata(manager, "com.demo")

    assert web_meta == {"channel": "web"}
    assert mobile_meta == {"channel": "mobile"}
