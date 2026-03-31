from app.plugins.models import PluginInfo, PluginManifest


def test_plugin_to_dict_preview_workbench_layout_defaults_to_default() -> None:
    plugin = PluginInfo(
        manifest=PluginManifest(
            id="com.test.default",
            name="Default Plugin",
            version="0.1.0",
        )
    )

    snapshot = plugin.to_dict()

    assert snapshot["preview"]["workbench_layout"] == "default"


def test_plugin_to_dict_preview_workbench_layout_supports_agent_preview() -> None:
    plugin = PluginInfo(
        manifest=PluginManifest(
            id="com.test.agent",
            name="Agent Plugin",
            version="0.1.0",
            preview={
                "workbench_layout": "agent_preview",
            },
        )
    )

    snapshot = plugin.to_dict()

    assert snapshot["preview"]["workbench_layout"] == "agent_preview"

