"""
DawnChat Plugin System

Provides plugin lifecycle management, environment isolation, and registry.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .env_manager import UVEnvManager
    from .manager import PluginManager
    from .models import PluginInfo, PluginManifest, PluginState
    from .plugin_log_service import PluginLogService
    from .registry import PluginRegistry


def get_plugin_manager():
    from .manager import get_plugin_manager as _get_plugin_manager

    return _get_plugin_manager()


def get_plugin_log_service():
    from .plugin_log_service import get_plugin_log_service as _get_plugin_log_service

    return _get_plugin_log_service()


def __getattr__(name: str) -> Any:
    if name == "PluginManager":
        from .manager import PluginManager

        return PluginManager
    if name == "PluginManifest":
        from .models import PluginManifest

        return PluginManifest
    if name == "PluginState":
        from .models import PluginState

        return PluginState
    if name == "PluginInfo":
        from .models import PluginInfo

        return PluginInfo
    if name == "PluginRegistry":
        from .registry import PluginRegistry

        return PluginRegistry
    if name == "PluginLogService":
        from .plugin_log_service import PluginLogService

        return PluginLogService
    if name == "UVEnvManager":
        from .env_manager import UVEnvManager

        return UVEnvManager
    raise AttributeError(f"module 'app.plugins' has no attribute '{name}'")

__all__ = [
    "PluginManager",
    "get_plugin_manager",
    "PluginManifest",
    "PluginState",
    "PluginInfo",
    "PluginRegistry",
    "PluginLogService",
    "UVEnvManager",
    "get_plugin_log_service",
]
