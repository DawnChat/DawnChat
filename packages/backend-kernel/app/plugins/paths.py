from __future__ import annotations

from pathlib import Path

from .models import PluginManifest


def _resolve_relative_child(base_dir: Path, raw_path: str, field_name: str) -> Path:
    value = str(raw_path or "").strip()
    if not value:
        return base_dir
    candidate = Path(value)
    if candidate.is_absolute():
        raise RuntimeError(f"manifest.{field_name} must be a relative path")
    resolved = (base_dir / candidate).resolve()
    base_resolved = base_dir.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as err:
        raise RuntimeError(f"manifest.{field_name} escapes plugin directory") from err
    return resolved


def resolve_plugin_source_root(manifest: PluginManifest) -> Path:
    plugin_path = str(manifest.plugin_path or "").strip()
    if not plugin_path:
        raise RuntimeError("Plugin path missing")
    base_dir = Path(plugin_path).resolve()
    runtime_root = str(manifest.runtime.root or "").strip()
    return _resolve_relative_child(base_dir, runtime_root, "runtime.root")


def resolve_plugin_frontend_dir(manifest: PluginManifest) -> Path:
    source_root = resolve_plugin_source_root(manifest)
    frontend_dir = str(manifest.preview.frontend_dir or "web-src").strip() or "web-src"
    return _resolve_relative_child(source_root, frontend_dir, "preview.frontend_dir")


def resolve_runtime_entry(manifest: PluginManifest, backend: str) -> Path:
    source_root = resolve_plugin_source_root(manifest)
    runtime_entry = str(manifest.runtime.entry or "").strip()
    if runtime_entry:
        return _resolve_relative_child(source_root, runtime_entry, "runtime.entry")

    normalized_backend = str(backend or "").strip().lower()
    if normalized_backend == "bun":
        for candidate in ("src/main.ts", "src/main.js", "src/index.ts", "src/index.js"):
            entry = source_root / candidate
            if entry.exists():
                return entry
        raise RuntimeError(f"Bun entry point not found under {source_root / 'src'}")

    entry_path = source_root / "src" / "main.py"
    if manifest.capabilities.gradio.enabled and manifest.capabilities.gradio.entry:
        entry_path = _resolve_relative_child(source_root, manifest.capabilities.gradio.entry, "capabilities.gradio.entry")
    elif manifest.capabilities.nicegui.enabled and manifest.capabilities.nicegui.entry:
        entry_path = _resolve_relative_child(source_root, manifest.capabilities.nicegui.entry, "capabilities.nicegui.entry")
    return entry_path

