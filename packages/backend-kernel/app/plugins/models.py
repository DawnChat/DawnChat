"""
DawnChat Plugin System - Data Models

Defines the data structures for plugin manifests, state, and metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel


def _detect_iwp_requirements(plugin_path: str | None) -> bool:
    root = str(plugin_path or "").strip()
    if not root:
        return False
    iwp_root = (Path(root).expanduser().resolve() / "InstructWare.iw")
    return iwp_root.exists() and iwp_root.is_dir()


class PluginState(str, Enum):
    """Plugin lifecycle states."""
    
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class PluginPreviewState(str, Enum):
    """Plugin preview lifecycle states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RELOADING = "reloading"
    ERROR = "error"


class GradioCapability(BaseModel):
    """Gradio capability configuration."""
    
    enabled: bool = False
    entry: Optional[str] = None


class NiceGUICapability(BaseModel):
    """NiceGUI capability configuration."""
    
    enabled: bool = False
    entry: Optional[str] = None


class CardsCapability(BaseModel):
    """Adaptive Cards capability configuration."""
    
    enabled: bool = False
    commands: list[dict[str, Any]] = []


class ChatCapability(BaseModel):
    """Chat mode capability configuration."""
    
    enabled: bool = False
    entry: Optional[str] = None


class PluginCapabilities(BaseModel):
    """Plugin capabilities configuration."""
    
    gradio: GradioCapability = GradioCapability()
    nicegui: NiceGUICapability = NiceGUICapability()
    cards: CardsCapability = CardsCapability()
    chat: ChatCapability = ChatCapability()
    tools: list[dict[str, Any]] = []


class PluginUIConfig(BaseModel):
    type: Optional[str] = None
    entry: Optional[str] = None
    framework: Optional[str] = None


class PluginRuntimeConfig(BaseModel):
    mode: Optional[str] = None
    backend: Optional[str] = None
    root: Optional[str] = None
    entry: Optional[str] = None
    isolated: bool = False


class PluginPreviewConfig(BaseModel):
    frontend_dir: Optional[str] = None
    workbench_layout: Literal["default", "agent_preview"] = "default"
    python_sidecar_enabled: bool = False


class OpenCodeInstructionPolicy(BaseModel):
    include_shared_rules: bool = True
    include_workspace_rules: bool = True


class OpenCodePluginConfig(BaseModel):
    instruction_policy: OpenCodeInstructionPolicy = OpenCodeInstructionPolicy()


class MobileConfig(BaseModel):
    """Mobile platform configuration."""
    
    enabled: bool = False


class PluginManifest(BaseModel):
    """
    Plugin manifest definition.
    
    Parsed from manifest.json in the plugin directory.
    """
    
    id: str
    name: str
    version: str
    app_type: str = "desktop"
    description: str = ""
    author: str = ""
    license: str = "MIT"
    
    sdk_version: str = "^1.0.0"
    min_host_version: str = "1.0.0"
    
    permissions: list[str] = []
    capabilities: PluginCapabilities = PluginCapabilities()
    mobile: MobileConfig = MobileConfig()
    ui: PluginUIConfig = PluginUIConfig()
    runtime: PluginRuntimeConfig = PluginRuntimeConfig()
    preview: PluginPreviewConfig = PluginPreviewConfig()
    opencode: OpenCodePluginConfig = OpenCodePluginConfig()
    
    icon: str = "📦"
    tags: list[str] = []
    
    # Runtime fields (not from manifest.json)
    plugin_path: Optional[str] = None
    is_official: bool = False


@dataclass
class PluginRuntimeInfo:
    """Runtime information for a running plugin."""
    
    process_id: Optional[int] = None
    port: Optional[int] = None
    started_at: Optional[datetime] = None
    health_check_url: Optional[str] = None
    gradio_url: Optional[str] = None


@dataclass
class PluginPreviewRuntimeInfo:
    """Runtime information for plugin preview mode."""

    state: PluginPreviewState = PluginPreviewState.STOPPED
    url: Optional[str] = None
    backend_port: Optional[int] = None
    frontend_port: Optional[int] = None
    log_session_id: Optional[str] = None
    error_message: Optional[str] = None
    frontend_mode: str = "dev"  # dev | dist
    deps_ready: bool = True
    install_status: str = "idle"  # idle | running | success | failed
    install_error_message: Optional[str] = None
    python_sidecar_port: Optional[int] = None
    python_sidecar_state: str = "stopped"
    python_sidecar_error_message: Optional[str] = None


@dataclass
class PluginInfo:
    """
    Complete plugin information including manifest and runtime state.
    """
    
    manifest: PluginManifest
    state: PluginState = PluginState.STOPPED
    runtime: PluginRuntimeInfo = field(default_factory=PluginRuntimeInfo)
    preview: PluginPreviewRuntimeInfo = field(default_factory=PluginPreviewRuntimeInfo)
    error_message: Optional[str] = None
    venv_path: Optional[str] = None
    source_type: str = "unknown"
    owner_user_id: str = ""
    owner_email: str = ""
    template_id: str = ""
    created_at: str = ""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "app_type": self.manifest.app_type,
            "description": self.manifest.description,
            "author": self.manifest.author,
            "icon": self.manifest.icon,
            "tags": self.manifest.tags,
            "state": self.state.value,
            "is_official": self.manifest.is_official,
            "plugin_path": self.manifest.plugin_path,
            "capabilities": {
                "gradio": self.manifest.capabilities.gradio.enabled,
                "cards": self.manifest.capabilities.cards.enabled,
                "chat": self.manifest.capabilities.chat.enabled,
                "tools": len(self.manifest.capabilities.tools) > 0,
            },
            "runtime": {
                "port": self.runtime.port,
                "gradio_url": self.runtime.gradio_url,
                "started_at": self.runtime.started_at.isoformat() if self.runtime.started_at else None,
            } if self.state == PluginState.RUNNING else None,
            "preview": {
                "state": self.preview.state.value,
                "url": self.preview.url,
                "backend_port": self.preview.backend_port,
                "frontend_port": self.preview.frontend_port,
                "log_session_id": self.preview.log_session_id,
                "error_message": self.preview.error_message,
                "frontend_mode": self.preview.frontend_mode,
                "deps_ready": self.preview.deps_ready,
                "install_status": self.preview.install_status,
                "install_error_message": self.preview.install_error_message,
                "python_sidecar_port": self.preview.python_sidecar_port,
                "python_sidecar_state": self.preview.python_sidecar_state,
                "python_sidecar_error_message": self.preview.python_sidecar_error_message,
                "workbench_layout": self.manifest.preview.workbench_layout,
                "has_iwp_requirements": _detect_iwp_requirements(self.manifest.plugin_path),
            },
            "error_message": self.error_message,
            "source_type": self.source_type,
            "owner_user_id": self.owner_user_id,
            "owner_email": self.owner_email,
            "template_id": self.template_id,
            "created_at": self.created_at,
        }


def build_plugin_workspace_profile(plugin: PluginInfo) -> dict[str, Any]:
    """
    Build a coding-agent-oriented workspace profile from the canonical plugin model.

    Keeping this logic in the plugin domain layer avoids API routes guessing whether
    they received a PluginInfo object or an already-serialized dict snapshot.
    """
    app_type = str(plugin.manifest.app_type or "desktop")
    plugin_path = str(plugin.manifest.plugin_path or "")
    runtime_root = str(plugin.manifest.runtime.root or "").strip().strip("/")
    root_prefix = f"{runtime_root}/" if runtime_root else ""
    frontend_dir = str(plugin.manifest.preview.frontend_dir or "web-src").strip().strip("/") or "web-src"
    frontend_src = f"{root_prefix}{frontend_dir}/src"

    if app_type == "web":
        preferred_entry = f"{frontend_src}/App.vue"
        preferred_directories = [
            frontend_src,
            f"{frontend_src}/components",
            f"{frontend_src}/views",
            f"{frontend_src}/composables",
            f"{frontend_src}/stores",
        ]
        hints = [
            "This is a pure frontend web plugin.",
            f"Prioritize edits under {frontend_dir} and do not assume src/main.py exists.",
        ]
    elif app_type == "mobile":
        preferred_entry = f"{frontend_src}/App.vue"
        preferred_directories = [
            frontend_src,
            f"{frontend_src}/components",
            f"{frontend_src}/views",
            f"{frontend_src}/composables",
            f"{frontend_src}/services",
        ]
        hints = [
            "This is a mobile plugin based on a frontend project.",
            f"Prioritize edits under {frontend_dir} and keep native capability calls behind service abstractions.",
            "Desktop preview validates UI flow; device-specific capabilities should be verified in mobile host.",
        ]
    else:
        default_entry = "src/main.py"
        if plugin.manifest.runtime.entry:
            default_entry = str(plugin.manifest.runtime.entry).strip() or default_entry
        preferred_entry = f"{root_prefix}{default_entry}".strip("/")
        entry_parent = str(Path(default_entry).parent).strip().strip("/")
        if not entry_parent:
            entry_parent = "src"
        preferred_directories = [f"{root_prefix}{entry_parent}".strip("/"), frontend_src]
        hints = ["This is a desktop plugin and may include both Python and Vue code."]

    return {
        "plugin_id": plugin.manifest.id,
        "app_type": app_type,
        "workspace_path": plugin_path,
        "preferred_entry": preferred_entry,
        "preferred_directories": preferred_directories,
        "hints": hints,
    }
