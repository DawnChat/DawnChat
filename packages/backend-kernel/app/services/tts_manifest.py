from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("tts_manifest")


@dataclass
class TTSModelManifestEntry:
    installed: bool = False
    path: str = ""
    hf_repo_id: str = ""
    installed_at: str = ""
    voices: List[str] = field(default_factory=list)


@dataclass
class TTSManifest:
    version: str = "1.0"
    models: Dict[str, TTSModelManifestEntry] = field(default_factory=dict)
    default_voice: str = "Emma"
    updated_at: str = ""

    @classmethod
    def get_manifest_path(cls) -> Path:
        return Config.MODELS_DIR / "tts_manifest.json"

    @classmethod
    def load(cls) -> "TTSManifest":
        manifest_path = cls.get_manifest_path()
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                models: Dict[str, TTSModelManifestEntry] = {}
                for key, entry_data in (data.get("models") or {}).items():
                    if isinstance(entry_data, dict):
                        models[str(key)] = TTSModelManifestEntry(
                            installed=bool(entry_data.get("installed", False)),
                            path=str(entry_data.get("path", "")),
                            hf_repo_id=str(entry_data.get("hf_repo_id", "")),
                            installed_at=str(entry_data.get("installed_at", "")),
                            voices=list(entry_data.get("voices") or []),
                        )
                return cls(
                    version=str(data.get("version", "1.0")),
                    models=models,
                    default_voice=str(data.get("default_voice", "Emma")),
                    updated_at=str(data.get("updated_at", "")),
                )
            except Exception as e:
                logger.warning(f"加载 TTS manifest 失败: {e}")

        return cls()

    def save(self) -> None:
        manifest_path = self.get_manifest_path()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = datetime.now().isoformat()
        data = {
            "version": self.version,
            "models": {k: asdict(v) for k, v in self.models.items()},
            "default_voice": self.default_voice,
            "updated_at": self.updated_at,
        }
        manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def set_model_installed(
        self,
        *,
        model_key: str,
        path: str,
        hf_repo_id: str,
        voices: Optional[List[str]] = None,
    ) -> None:
        self.models[str(model_key)] = TTSModelManifestEntry(
            installed=True,
            path=str(path),
            hf_repo_id=str(hf_repo_id),
            installed_at=datetime.now().isoformat(),
            voices=list(voices or []),
        )
        self.save()

    def set_model_uninstalled(self, *, model_key: str) -> None:
        key = str(model_key)
        if key in self.models:
            self.models[key].installed = False
            self.save()

    def is_model_installed(self, *, model_key: str) -> bool:
        entry = self.models.get(str(model_key))
        return bool(entry.installed) if entry else False

    def get_model_path(self, *, model_key: str) -> Optional[str]:
        entry = self.models.get(str(model_key))
        return str(entry.path) if entry and entry.installed else None
