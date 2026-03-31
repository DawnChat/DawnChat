from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    api_host: str
    api_port: int
    test_mode: bool
    data_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class PluginSettings:
    root_dir: Path
    sources_dir: Path
    data_dir: Path
    models_dir: Path
    download_dir: Path
    preview_enabled: bool
    preview_bind_host: str
    preview_port_range: tuple[int, int]


@dataclass(frozen=True)
class AgentSettings:
    runtime: str
    default_agent: str
    max_steps: int
    context_length: int

