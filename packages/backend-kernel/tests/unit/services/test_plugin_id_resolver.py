from __future__ import annotations

import pytest

from app.services import plugin_id_resolver as resolver_module
from app.services.plugin_id_resolver import PluginIdResolveError, PluginIdResolver


class _ManagerStub:
    def __init__(self, registered_ids: list[str]) -> None:
        self._registered_ids = set(registered_ids)

    def get_plugin_snapshot(self, plugin_id: str):
        if plugin_id in self._registered_ids:
            return {"id": plugin_id}
        return None

    def list_plugins(self):
        return [{"id": plugin_id} for plugin_id in sorted(self._registered_ids)]


def test_resolve_exact_id(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(["com.demo.plugin"])
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    resolver = PluginIdResolver()

    resolved = resolver.resolve("com.demo.plugin")

    assert resolved.canonical_plugin_id == "com.demo.plugin"
    assert resolved.resolve_source == "exact"


def test_resolve_path_basename_id(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(["com.demo.plugin"])
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    resolver = PluginIdResolver()

    resolved = resolver.resolve("/Users/test/plugins/com.demo.plugin")

    assert resolved.canonical_plugin_id == "com.demo.plugin"
    assert resolved.resolve_source == "path_basename"


def test_resolve_safe_name_id(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(["com.demo.plugin"])
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    resolver = PluginIdResolver()

    resolved = resolver.resolve("com_demo_plugin")

    assert resolved.canonical_plugin_id == "com.demo.plugin"
    assert resolved.resolve_source == "safe_name"


def test_resolve_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(["com.demo.plugin"])
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    resolver = PluginIdResolver()

    with pytest.raises(PluginIdResolveError) as exc:
        resolver.resolve("unknown_plugin")

    assert exc.value.code == "plugin_not_found"


def test_resolve_safe_name_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(["a.b/c", "a/b.c"])
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    resolver = PluginIdResolver()

    with pytest.raises(PluginIdResolveError) as exc:
        resolver.resolve("a_b_c")

    assert exc.value.code == "ambiguous_plugin_id"
    assert exc.value.details == {"candidates": ["a.b/c", "a/b.c"]}
