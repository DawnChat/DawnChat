from __future__ import annotations

from dataclasses import dataclass
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type

from app.config import Config
from app.services.mlx_server_manager import get_mlx_server_manager
from app.services.model_manager import get_model_manager
from app.utils.logger import get_logger

logger = get_logger("mlx_provider")

VISION_MARKERS = (
    "qwen2_vl",
    "qwen2.5_vl",
    "qwen-vl",
    "llava",
    "llava_next",
    "llava-onevision",
    "idefics",
    "pixtral",
    "paligemma",
    "internvl",
    "glm-4v",
    "phi3_v",
    "mllama",
    "minicpm-v",
)
VISION_KEYS = {
    "vision_config",
    "image_processor_type",
    "vision_tower",
    "mm_vision_tower",
    "mm_projector",
    "image_token_index",
    "vision_hidden_size",
    "image_size",
    "patch_size",
    "vision_encoder",
    "visual",
}


def is_mlx_vision_config(config: Dict[str, Any]) -> bool:
    if not config:
        return False
    model_type = str(config.get("model_type") or "").lower()
    architectures = [str(a).lower() for a in (config.get("architectures") or []) if a]
    if any(marker in model_type for marker in VISION_MARKERS):
        return True
    if any(any(marker in arch for marker in VISION_MARKERS) for arch in architectures):
        return True
    return any(key in config for key in VISION_KEYS)


@dataclass(frozen=True)
class MLXResolvedTarget:
    mode: str
    is_vision: bool
    api_base: Optional[str]
    litellm_model: Optional[str]
    load_path: Path


class MLXProvider:
    def __init__(self):
        self._server_manager = get_mlx_server_manager()

    def _resolve_load_path(self, model_id: str) -> Path:
        manager = get_model_manager()
        path = manager.get_model_path(model_id)
        if not path:
            raise ValueError(f"模型文件不存在: {model_id}")
        load_path = path
        if path.is_file():
            parent = path.parent
            if (
                (parent / "tokenizer.json").exists()
                or (parent / "tokenizer.model").exists()
                or (parent / "config.json").exists()
            ):
                load_path = parent
        return load_path

    def _read_model_config(self, load_path: Path) -> Dict[str, Any]:
        try:
            config_path = load_path / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            return {}
        return {}

    def _is_vision_config(self, config: Dict[str, Any]) -> bool:
        return is_mlx_vision_config(config)

    async def resolve_target(self, model_id: str) -> MLXResolvedTarget:
        mode = (Config.MLX_PROVIDER_MODE or "http").lower()
        if mode not in {"http", "inprocess"}:
            mode = "http"

        load_path = self._resolve_load_path(model_id)
        config = self._read_model_config(load_path if load_path.is_dir() else load_path.parent)
        is_vision = self._is_vision_config(config)

        if mode == "inprocess":
            mlx_local_provider_cls: Optional[Type[Any]] = None
            try:
                mod = importlib.import_module("app.ai.mlx_local_provider")
                candidate = getattr(mod, "MLXLocalProvider", None)
                if isinstance(candidate, type):
                    mlx_local_provider_cls = candidate
            except Exception:
                mlx_local_provider_cls = None

            if mlx_local_provider_cls is None:
                raise ValueError("未安装 MLX 运行时，无法使用 MLX in-process 模式")
            return MLXResolvedTarget(
                mode="inprocess",
                is_vision=is_vision,
                api_base=None,
                litellm_model=None,
                load_path=load_path,
            )

        if is_vision:
            ok = await self._server_manager.ensure_vlm_ready()
            if not ok:
                raise ValueError(f"mlx-vlm 启动失败，请查看日志: {Config.LOGS_DIR / 'mlx_vlm.log'}")
            api_base = self._server_manager.vlm.get_api_base()
            return MLXResolvedTarget(
                mode="http",
                is_vision=True,
                api_base=api_base,
                litellm_model=f"openai/{model_id}",
                load_path=load_path,
            )

        ok = await self._server_manager.ensure_lm_ready(load_path)
        if not ok:
            raise ValueError(f"mlx-lm 启动失败，请查看日志: {Config.LOGS_DIR / 'mlx_lm.log'}")
        api_base = self._server_manager.lm.get_api_base()
        return MLXResolvedTarget(
            mode="http",
            is_vision=False,
            api_base=api_base,
            litellm_model=f"openai/{model_id}",
            load_path=load_path,
        )
