from pathlib import Path
from types import SimpleNamespace

import pytest

from app.plugins.preview_manager import PluginPreviewManager


def _build_plugin() -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(
            id="com.demo.app",
            runtime=SimpleNamespace(root="_ir", entry="backend/entry/main.ts"),
            preview=SimpleNamespace(frontend_dir="frontend/web-src", python_sidecar_enabled=False),
        )
    )


def _build_bun_session() -> SimpleNamespace:
    return SimpleNamespace(
        backend_kind="bun",
        plugin_path=Path("/tmp/plugin-demo"),
        entry_path=Path("/tmp/plugin-demo/_ir/backend/entry/main.ts"),
    )


def test_should_restart_backend_for_bun_backend_code_change() -> None:
    plugin = _build_plugin()
    session = _build_bun_session()
    changed = ["/tmp/plugin-demo/_ir/backend/services/runtime.ts"]

    assert PluginPreviewManager._should_restart_backend(plugin, session, changed) is True


def test_should_not_restart_backend_for_frontend_hmr_change() -> None:
    plugin = _build_plugin()
    session = _build_bun_session()
    changed = ["/tmp/plugin-demo/_ir/frontend/web-src/src/App.vue"]

    assert PluginPreviewManager._should_restart_backend(plugin, session, changed) is False


def test_should_restart_backend_for_backend_package_lock_change() -> None:
    plugin = _build_plugin()
    session = _build_bun_session()
    changed = ["/tmp/plugin-demo/_ir/backend/bun.lock"]

    assert PluginPreviewManager._should_restart_backend(plugin, session, changed) is True


def test_resolve_python_sidecar_entry_path_returns_none_when_disabled() -> None:
    plugin = _build_plugin()
    source_root = Path("/tmp/plugin-demo/_ir")

    assert PluginPreviewManager.resolve_python_sidecar_entry_path(plugin, source_root) is None


@pytest.mark.asyncio
async def test_start_backend_process_does_not_fail_when_sidecar_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginPreviewManager(SimpleNamespace())
    plugin = _build_plugin()
    session = SimpleNamespace(
        backend_kind="bun",
        python_sidecar_entry_path=Path("/tmp/plugin-demo/_ir/python/entry/main.py"),
        python_sidecar_port=18081,
        python_sidecar_state="stopped",
        python_sidecar_error_message=None,
    )

    async def _start_bun_backend_process(_plugin, _session):
        return None

    async def _start_python_sidecar_process(_plugin, _session):
        raise RuntimeError("sidecar boom")

    monkeypatch.setattr(manager, "start_bun_backend_process", _start_bun_backend_process)
    monkeypatch.setattr(manager, "start_python_sidecar_process", _start_python_sidecar_process)

    await manager.start_backend_process(plugin, session)

    assert session.python_sidecar_state == "error"
    assert "sidecar boom" in str(session.python_sidecar_error_message or "")
