from types import SimpleNamespace

import pytest

from app.plugins.models import PluginPreviewState, PluginState
from app.plugins.application.preview_application_service import PluginPreviewApplicationService


class _RegistryDouble:
    def __init__(self, plugin):
        self._plugin = plugin

    def get(self, plugin_id: str):
        if self._plugin and plugin_id == "com.demo.app":
            return self._plugin
        return None


class _PreviewManagerDouble:
    def __init__(self, *, start_ok: bool = True) -> None:
        self.start_ok = start_ok
        self.start_calls = 0
        self.stop_calls = 0
        self.retry_calls = 0

    async def start_preview(self, plugin) -> bool:
        self.start_calls += 1
        if self.start_ok:
            plugin.preview.url = "http://127.0.0.1:5173/"
        return self.start_ok

    async def stop_preview(self, plugin) -> bool:
        self.stop_calls += 1
        return True

    async def retry_preview_frontend_install(self, plugin) -> bool:
        self.retry_calls += 1
        return True


def _build_plugin(*, state: PluginState = PluginState.STOPPED):
    return SimpleNamespace(
        state=state,
        manifest=SimpleNamespace(
            app_type="mobile",
            preview=SimpleNamespace(workbench_layout="agent_preview"),
        ),
        preview=SimpleNamespace(
            state=PluginPreviewState.RUNNING,
            url="http://127.0.0.1:5173/",
            backend_port=6001,
            frontend_port=5173,
            log_session_id="s1",
            error_message="",
            frontend_mode="dev",
            deps_ready=True,
            install_status="ready",
            install_error_message="",
            python_sidecar_port=6101,
            python_sidecar_state="running",
            python_sidecar_error_message="",
        ),
        runtime=SimpleNamespace(port=7001, gradio_url=None),
    )


@pytest.mark.asyncio
async def test_start_preview_stops_runtime_when_plugin_running() -> None:
    plugin = _build_plugin(state=PluginState.RUNNING)
    preview_manager = _PreviewManagerDouble(start_ok=True)
    stop_calls: list[str] = []

    async def _stop_runtime(plugin_id: str) -> bool:
        stop_calls.append(plugin_id)
        return True

    service = PluginPreviewApplicationService(
        _RegistryDouble(plugin),
        preview_manager,
        _stop_runtime,
    )

    url = await service.start_plugin_preview("com.demo.app")

    assert url == "http://127.0.0.1:5173/"
    assert stop_calls == ["com.demo.app"]
    assert preview_manager.start_calls == 1


def test_resolve_mcp_endpoint_prefers_preview_over_runtime() -> None:
    plugin = _build_plugin(state=PluginState.RUNNING)
    service = PluginPreviewApplicationService(
        _RegistryDouble(plugin),
        _PreviewManagerDouble(),
        lambda _: None,
        lambda _plugin_id: True,
    )

    endpoint = service.resolve_mcp_endpoint("com.demo.app")

    assert endpoint == {"port": 6001, "source": "preview"}


def test_resolve_mcp_endpoints_includes_python_sidecar() -> None:
    plugin = _build_plugin(state=PluginState.RUNNING)
    service = PluginPreviewApplicationService(
        _RegistryDouble(plugin),
        _PreviewManagerDouble(),
        lambda _: None,
        lambda _plugin_id: True,
    )

    endpoints = service.resolve_mcp_endpoints("com.demo.app")

    assert endpoints == {
        "backend": {"port": 6001, "source": "preview"},
        "python_sidecar": {"port": 6101, "source": "preview_python_sidecar"},
    }


def test_get_plugin_preview_status_includes_workbench_layout() -> None:
    plugin = _build_plugin()
    service = PluginPreviewApplicationService(
        _RegistryDouble(plugin),
        _PreviewManagerDouble(),
        lambda _: None,
        lambda _plugin_id: True,
    )

    payload = service.get_plugin_preview_status("com.demo.app")

    assert payload is not None
    assert payload["workbench_layout"] == "agent_preview"
    assert payload["has_iwp_requirements"] is True


def test_get_plugin_runtime_info_includes_python_sidecar_status(monkeypatch: pytest.MonkeyPatch) -> None:
    plugin = _build_plugin()
    service = PluginPreviewApplicationService(
        _RegistryDouble(plugin),
        _PreviewManagerDouble(),
        lambda _: None,
    )
    monkeypatch.setattr(
        "app.plugins.application.preview_application_service.Config.get_bun_binary",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.plugins.application.preview_application_service.Config.get_uv_binary",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.plugins.application.preview_application_service.Config.get_pbs_python",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.plugins.application.preview_application_service.get_tts_runtime_service",
        lambda: SimpleNamespace(get_plugin_runtime_state=lambda _plugin_id: {"state": "available", "mode": "manual"}),
    )

    payload = service.get_plugin_runtime_info("com.demo.app")

    assert payload is not None
    assert "python" in payload["environment"]
    assert payload["environment"]["python"] == {
        "status": "running",
        "available": False,
        "sidecar_running": True,
        "sidecar_port": 6101,
        "sidecar_error_message": "",
        "pbs_python": "",
        "pbs_python_exists": False,
        "uv_binary": "",
        "uv_binary_exists": False,
    }
    assert payload["python_sidecar"]["state"] == "running"
    assert payload["mcp_endpoints"]["python_sidecar"] == {"port": 6101, "source": "preview_python_sidecar"}
    assert payload["tts"] == {"state": "available", "mode": "manual"}
