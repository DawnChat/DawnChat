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


def _create_dist_ready_sdk_package(path: Path, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        (
            "{\n"
            f'  "name": "{name}",\n'
            '  "main": "./dist/index.js",\n'
            '  "types": "./dist/index.d.ts",\n'
            '  "exports": {\n'
            '    ".": {\n'
            '      "types": "./dist/index.d.ts",\n'
            '      "import": "./dist/index.js"\n'
            "    }\n"
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    dist_dir = path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.js").write_text("export {};\n", encoding="utf-8")
    (dist_dir / "index.d.ts").write_text("export {};\n", encoding="utf-8")


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


def test_probe_target_host_maps_wildcard_to_loopback() -> None:
    assert PluginPreviewManager._probe_target_host("0.0.0.0") == "127.0.0.1"
    assert PluginPreviewManager._probe_target_host("127.0.0.1") == "127.0.0.1"


@pytest.mark.asyncio
async def test_wait_frontend_reachable_succeeds_after_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginPreviewManager(SimpleNamespace())
    attempts = {"count": 0}

    async def _fake_probe(_host: str, _port: int, timeout_seconds: float = 0.8) -> bool:
        attempts["count"] += 1
        del timeout_seconds
        return attempts["count"] >= 2

    monkeypatch.setattr(manager, "_probe_frontend_reachable", _fake_probe)

    ready = await manager._wait_frontend_reachable(
        bind_host="127.0.0.1",
        port=17961,
        timeout_seconds=0.6,
        interval_seconds=0.05,
    )

    assert ready is True
    assert attempts["count"] >= 2


@pytest.mark.asyncio
async def test_wait_frontend_reachable_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginPreviewManager(SimpleNamespace())

    async def _fake_probe(_host: str, _port: int, timeout_seconds: float = 0.8) -> bool:
        del timeout_seconds
        return False

    monkeypatch.setattr(manager, "_probe_frontend_reachable", _fake_probe)

    ready = await manager._wait_frontend_reachable(
        bind_host="127.0.0.1",
        port=17961,
        timeout_seconds=0.2,
        interval_seconds=0.05,
    )

    assert ready is False


def test_apply_preview_runtime_fields_syncs_frontend_probe_state() -> None:
    plugin = SimpleNamespace(
        preview=SimpleNamespace(
            backend_port=None,
            frontend_port=None,
            log_session_id=None,
            frontend_mode="dist",
            deps_ready=False,
            frontend_reachable=None,
            frontend_last_probe_at=None,
            install_status="idle",
            install_error_message=None,
            python_sidecar_port=None,
            python_sidecar_state="stopped",
            python_sidecar_error_message=None,
        )
    )
    session = SimpleNamespace(
        backend_port=17001,
        frontend_port=17002,
        log_session_id="s1",
        frontend_mode="dev",
        deps_ready=True,
        frontend_reachable=True,
        frontend_last_probe_at="2026-04-03T06:54:27Z",
        install_status="success",
        install_error_message=None,
        python_sidecar_port=None,
        python_sidecar_state="stopped",
        python_sidecar_error_message=None,
    )

    PluginPreviewManager._apply_preview_runtime_fields(plugin, session)

    assert plugin.preview.frontend_port == 17002
    assert plugin.preview.frontend_reachable is True
    assert plugin.preview.frontend_last_probe_at == "2026-04-03T06:54:27Z"


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


@pytest.mark.asyncio
async def test_wait_frontend_reachable_succeeds_with_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginPreviewManager(SimpleNamespace())
    results = iter([False, True])

    async def _probe(_host: str, _port: int, timeout_seconds: float = 0.8) -> bool:
        del timeout_seconds
        return next(results)

    monkeypatch.setattr(manager, "_probe_frontend_reachable", _probe)

    ready = await manager._wait_frontend_reachable(
        bind_host="127.0.0.1",
        port=17961,
        timeout_seconds=1.0,
        interval_seconds=0.01,
    )

    assert ready is True


@pytest.mark.asyncio
async def test_wait_frontend_reachable_timeout_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PluginPreviewManager(SimpleNamespace())

    async def _probe(_host: str, _port: int, timeout_seconds: float = 0.8) -> bool:
        del timeout_seconds
        return False

    monkeypatch.setattr(manager, "_probe_frontend_reachable", _probe)

    ready = await manager._wait_frontend_reachable(
        bind_host="127.0.0.1",
        port=17961,
        timeout_seconds=0.05,
        interval_seconds=0.01,
    )

    assert ready is False


def test_apply_preview_runtime_fields_syncs_frontend_probe_state_with_namespace() -> None:
    session = SimpleNamespace(
        backend_port=6001,
        frontend_port=5173,
        log_session_id="s1",
        frontend_mode="dev",
        deps_ready=True,
        frontend_reachable=False,
        frontend_last_probe_at="2026-04-03T06:54:27Z",
        install_status="running",
        install_error_message="pending",
        python_sidecar_port=None,
        python_sidecar_state="stopped",
        python_sidecar_error_message=None,
    )
    plugin = SimpleNamespace(
        preview=SimpleNamespace(
            backend_port=None,
            frontend_port=None,
            log_session_id=None,
            frontend_mode="dist",
            deps_ready=False,
            frontend_reachable=None,
            frontend_last_probe_at=None,
            install_status="idle",
            install_error_message=None,
            python_sidecar_port=None,
            python_sidecar_state="stopped",
            python_sidecar_error_message=None,
        )
    )

    PluginPreviewManager._apply_preview_runtime_fields(plugin, session)

    assert plugin.preview.frontend_reachable is False
    assert plugin.preview.frontend_last_probe_at == "2026-04-03T06:54:27Z"


def test_validate_assistant_sdk_dependencies_rejects_workspace_specifier(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
        {
          "dependencies": {
            "@dawnchat/assistant-core": "workspace:*"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="not rewritten before preview install"):
        PluginPreviewManager._validate_assistant_sdk_dependencies(package_json)


def test_validate_assistant_sdk_dependencies_rejects_missing_file_target(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
        {
          "dependencies": {
            "@dawnchat/assistant-core": "file:../vendor/assistant-sdk/assistant-core"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing or incomplete dist bundles"):
        PluginPreviewManager._validate_assistant_sdk_dependencies(package_json)


def test_validate_assistant_sdk_dependencies_rejects_incomplete_dist_bundle(tmp_path: Path) -> None:
    sdk_dir = tmp_path / "vendor" / "assistant-sdk" / "assistant-core"
    _create_dist_ready_sdk_package(sdk_dir, "@dawnchat/assistant-core")
    (sdk_dir / "dist" / "index.js").unlink()

    package_json = tmp_path / "package.json"
    package_json.write_text(
        """
        {
          "dependencies": {
            "@dawnchat/assistant-core": "file:./vendor/assistant-sdk/assistant-core"
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="dist incomplete"):
        PluginPreviewManager._validate_assistant_sdk_dependencies(package_json)
