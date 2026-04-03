from __future__ import annotations

from app.plugin_ui_bridge.models import BridgeOperation
from app.plugin_ui_bridge.service import PluginUIBridgeService
import app.plugin_ui_bridge.service as service_module


def test_resolve_dispatch_timeout_uses_default_timeout(monkeypatch) -> None:
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_TIMEOUT_SECONDS", 15.0)
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_SECONDS", 130.0)
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_SECONDS", 5.0)

    timeout_seconds = PluginUIBridgeService._resolve_dispatch_timeout_seconds(
        BridgeOperation.DESCRIBE,
        {},
    )

    assert timeout_seconds == 15.0


def test_resolve_dispatch_timeout_extends_wait_timeout(monkeypatch) -> None:
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_TIMEOUT_SECONDS", 15.0)
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_SECONDS", 90.0)
    monkeypatch.setattr(service_module.Config, "PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_SECONDS", 5.0)

    timeout_seconds = PluginUIBridgeService._resolve_dispatch_timeout_seconds(
        BridgeOperation.CAPABILITY_INVOKE,
        {
            "function": "assistant.event.wait",
            "payload": {
                "timeout_ms": 120000,
            },
        },
    )

    assert timeout_seconds == 125.0
