"""
DawnChat Plugin System - Plugin Registry

Manages the collection of installed plugins and their metadata.
"""

import json
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

from .models import PluginInfo, PluginManifest, PluginState

logger = get_logger("plugin_registry")


class PluginRegistry:
    """
    Registry of installed plugins.
    
    Responsible for:
    - Scanning plugin directories for installed plugins
    - Parsing and validating plugin manifests
    - Maintaining the list of registered plugins
    """
    
    def __init__(self):
        self._plugins: dict[str, PluginInfo] = {}
        logger.info("PluginRegistry initialized")
    
    @property
    def plugins(self) -> dict[str, PluginInfo]:
        """Get all registered plugins."""
        return dict(self._plugins)
    
    def get(self, plugin_id: str) -> Optional[PluginInfo]:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()
    
    def register(self, plugin_info: PluginInfo) -> None:
        """Register a plugin."""
        self._plugins[plugin_info.manifest.id] = plugin_info
        logger.info(f"Registered plugin: {plugin_info.manifest.id}")
    
    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin."""
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            logger.info(f"Unregistered plugin: {plugin_id}")
            return True
        return False
    
    def update_state(self, plugin_id: str, state: PluginState, error: Optional[str] = None) -> bool:
        """Update a plugin's state."""
        if plugin_id not in self._plugins:
            return False
        
        self._plugins[plugin_id].state = state
        if error is not None:
            self._plugins[plugin_id].error_message = error
        elif state != PluginState.ERROR:
            self._plugins[plugin_id].error_message = None
        
        logger.debug(f"Plugin {plugin_id} state updated to {state.value}")
        return True
    
    def scan_directory(self, directory: Path, is_official: bool = False) -> int:
        """
        Scan a directory for plugins and register them.
        
        Args:
            directory: Directory to scan
            is_official: Whether these are official (built-in) plugins
        
        Returns:
            Number of plugins registered
        """
        if not directory.exists():
            logger.warning(f"Plugin directory does not exist: {directory}")
            return 0
        
        count = 0
        for item in directory.iterdir():
            if not item.is_dir():
                continue
            
            manifest_path = item / "manifest.json"
            if not manifest_path.exists():
                logger.debug(f"Skipping {item.name}: no manifest.json")
                continue
            
            try:
                manifest = self._parse_manifest(manifest_path)
                manifest.plugin_path = str(item)
                manifest.is_official = is_official
                
                plugin_info = PluginInfo(
                    manifest=manifest,
                    state=PluginState.STOPPED,
                )
                
                self.register(plugin_info)
                count += 1
                
            except Exception as e:
                logger.error(f"Failed to parse manifest for {item.name}: {e}")
        
        logger.info(f"Scanned {directory}: found {count} plugins")
        return count
    
    def _parse_manifest(self, manifest_path: Path) -> PluginManifest:
        """Parse a plugin manifest file."""
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return PluginManifest(**data)
    
    def list_all(self) -> list[dict]:
        """List all plugins as dictionaries."""
        return [info.to_dict() for info in self._plugins.values()]
    
    def list_by_state(self, state: PluginState) -> list[PluginInfo]:
        """List plugins in a specific state."""
        return [info for info in self._plugins.values() if info.state == state]

