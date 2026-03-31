"""
口语评分模型管理器

负责 Wav2Vec2 模型的下载和状态管理，用于 EchoFlow 插件的发音评分功能。

支持功能：
- 模型下载（通过通用 HF 下载器）
- 断点续传/暂停/恢复
- 模型安装状态检查
- 多规格模型支持

设计原则：
- 复用通用 HuggingFaceDownloadManager
- 单例模式管理
- 模型加载由插件自行处理（在其 venv 中）
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Config
from app.services.hf_download_v2 import HFDownloadManagerV2, get_hf_download_manager_v2
from app.utils.logger import get_logger

logger = get_logger("scoring")


# ============================================================================
# Wav2Vec2 模型配置
# ============================================================================

class ScoringModelSize(str, Enum):
    """Wav2Vec2 模型规格"""
    BASE = "base"           # ~380MB, 推荐
    LARGE = "large"         # ~1.3GB, 更高精度


@dataclass
class ScoringModelInfo:
    """Wav2Vec2 模型信息"""
    size: ScoringModelSize
    hf_repo_id: str
    name: str
    description: str
    size_mb: int


# 模型仓库配置
SCORING_MODELS: Dict[ScoringModelSize, ScoringModelInfo] = {
    ScoringModelSize.BASE: ScoringModelInfo(
        size=ScoringModelSize.BASE,
        hf_repo_id="facebook/wav2vec2-base-960h",
        name="Wav2Vec2 Base",
        description="基础模型，适合大多数场景，平衡速度与质量",
        size_mb=380,
    ),
    ScoringModelSize.LARGE: ScoringModelInfo(
        size=ScoringModelSize.LARGE,
        hf_repo_id="facebook/wav2vec2-large-960h",
        name="Wav2Vec2 Large",
        description="大型模型，更高精度，需要更多计算资源",
        size_mb=1300,
    ),
}


# 模型类型标识（用于 HF 下载管理器）
MODEL_TYPE = "scoring"


# ============================================================================
# 口语评分模型管理器（单例）
# ============================================================================

class ScoringManager:
    """
    口语评分模型管理器（单例）
    
    职责：
    1. 模型下载管理（委托给通用 HF 下载器）
    2. 模型安装状态检查
    3. 提供模型信息查询
    
    注意：模型加载和推理由 EchoFlow 插件自行处理
    """
    
    _instance: Optional['ScoringManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 使用 V2 下载管理器
        self._hf_manager: HFDownloadManagerV2 = get_hf_download_manager_v2()
        
        # 确保模型目录存在
        self._models_dir = Config.DATA_DIR / "models" / "scoring"
        self._models_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("口语评分模型管理器已初始化")
    
    # ========== 模型信息查询 ==========
    
    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有可用的 Wav2Vec2 模型"""
        models = []
        for size, info in SCORING_MODELS.items():
            model_dir = self._models_dir / size.value
            is_installed = self._check_model_installed(model_dir)
            
            # 检查是否正在下载
            progress = self._hf_manager.get_progress(MODEL_TYPE, size.value)
            is_downloading = progress.get("status") in ["pending", "downloading"]
            download_progress = progress.get("progress", 0) if is_downloading else 0
            
            models.append({
                "id": size.value,
                "name": info.name,
                "hf_repo_id": info.hf_repo_id,
                "description": info.description,
                "size_mb": info.size_mb,
                "installed": is_installed,
                "downloading": is_downloading,
                "progress": download_progress,
                "path": str(model_dir) if is_installed else None,
            })
        
        return models
    
    def _check_model_installed(self, model_dir: Path) -> bool:
        """检查模型是否已安装"""
        if not model_dir.exists():
            return False
        
        # 检查必要文件（Wav2Vec2 模型格式）
        # pytorch_model.bin 或 model.safetensors + config.json
        has_model_file = (
            (model_dir / "pytorch_model.bin").exists() or 
            (model_dir / "model.safetensors").exists()
        )
        has_config = (model_dir / "config.json").exists()
        
        return has_model_file and has_config
    
    def get_installed_models(self) -> List[str]:
        """获取已安装的模型列表"""
        installed = []
        for size in ScoringModelSize:
            model_dir = self._models_dir / size.value
            if self._check_model_installed(model_dir):
                installed.append(size.value)
        return installed
    
    def get_default_model(self) -> Optional[str]:
        """获取默认使用的模型（返回已安装的最优模型）"""
        # 按优先级排序（从大到小）
        priority = [
            ScoringModelSize.LARGE,
            ScoringModelSize.BASE,
        ]
        
        for size in priority:
            model_dir = self._models_dir / size.value
            if self._check_model_installed(model_dir):
                return size.value
        
        return None
    
    def get_model_path(self, model_size: str) -> Optional[Path]:
        """获取模型路径"""
        model_dir = self._models_dir / model_size
        if self._check_model_installed(model_dir):
            return model_dir
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        installed = self.get_installed_models()
        default_model = self.get_default_model()
        
        return {
            "available": len(installed) > 0,
            "installed_models": installed,
            "default_model": default_model,
            "models_dir": str(self._models_dir),
        }
    
    # ========== 下载相关（委托给通用下载器）==========
    
    async def download_model(
        self,
        model_size: str,
        use_mirror: Optional[bool] = None,
        resume: bool = False
    ) -> dict:
        """
        下载 Wav2Vec2 模型（使用 snapshot_download 下载整个仓库）
        
        Args:
            model_size: 模型规格 (base/large)
            use_mirror: 是否使用镜像
            resume: 是否为恢复下载
        
        Returns:
            下载启动状态
        """
        try:
            size_enum = ScoringModelSize(model_size)
        except ValueError:
            return {
                "status": "error",
                "message": f"不支持的模型规格: {model_size}，可选: {[s.value for s in ScoringModelSize]}"
            }
        
        model_info = SCORING_MODELS[size_enum]
        save_dir = self._models_dir / model_size
        
        # 检查是否已安装
        if self._check_model_installed(save_dir):
            return {
                "status": "already_installed",
                "message": f"模型 {model_size} 已安装",
                "path": str(save_dir),
            }
        
        logger.info(f"📥 启动 Wav2Vec2 {model_size} 下载任务")
        
        return await self._hf_manager.start_download(
            model_type=MODEL_TYPE,
            model_id=model_size,
            hf_repo_id=model_info.hf_repo_id,
            save_dir=save_dir,
            use_mirror=use_mirror,
            resume=resume,
        )
    
    def get_download_progress(self, model_size: str) -> dict:
        """获取下载进度"""
        return self._hf_manager.get_progress(MODEL_TYPE, model_size)
    
    async def request_pause(self, model_size: str) -> dict:
        """请求暂停下载"""
        return await self._hf_manager.request_pause(MODEL_TYPE, model_size)
    
    async def request_cancel(self, model_size: str) -> dict:
        """请求取消下载"""
        return await self._hf_manager.request_cancel(MODEL_TYPE, model_size)
    
    def get_pending_downloads(self) -> list:
        """获取所有可恢复的下载任务"""
        all_tasks = self._hf_manager.get_pending_downloads()
        # 过滤口语评分相关任务
        return [
            {
                "model_size": task["model_id"],
                "hf_repo_id": task["hf_repo_id"],
                "total_bytes": task.get("total_bytes", 0),
                "downloaded_bytes": task.get("downloaded_bytes", 0),
                "progress": task.get("progress", 0),
                "status": task.get("status", ""),
                "error_message": task.get("error_message")
            }
            for task in all_tasks
            if task.get("model_type") == MODEL_TYPE
        ]
    
    def is_download_active(self, model_size: str) -> bool:
        """检查下载是否活跃"""
        return self._hf_manager.is_active(MODEL_TYPE, model_size)
    
    async def delete_model(self, model_size: str) -> dict:
        """删除已安装的模型"""
        try:
            ScoringModelSize(model_size)
        except ValueError:
            return {
                "status": "error",
                "message": f"不支持的模型规格: {model_size}"
            }
        
        model_dir = self._models_dir / model_size
        
        if not model_dir.exists():
            return {
                "status": "not_found",
                "message": f"模型 {model_size} 未安装"
            }
        
        try:
            import shutil
            shutil.rmtree(model_dir)
            logger.info(f"🗑️ 已删除模型: {model_size}")
            return {
                "status": "deleted",
                "message": f"模型 {model_size} 已删除"
            }
        except Exception as e:
            logger.error(f"删除模型失败: {e}")
            return {
                "status": "error",
                "message": str(e)
            }


# ============================================================================
# 全局单例
# ============================================================================

_scoring_manager: Optional[ScoringManager] = None


def get_scoring_manager() -> ScoringManager:
    """获取口语评分模型管理器单例"""
    global _scoring_manager
    if _scoring_manager is None:
        _scoring_manager = ScoringManager()
    return _scoring_manager



