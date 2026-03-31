"""
NLTK 数据管理器
负责管理 NLTK 数据的下载和状态检查
"""

import logging
from typing import Any, Dict, Optional

import nltk

from app.config import Config

logger = logging.getLogger(__name__)

# 需要管理的 NLTK 资源列表
REQUIRED_RESOURCES = [
    {
        "id": "cmudict",
        "name": "CMU Dict",
        "path": "corpora/cmudict",
        "description": "卡内基梅隆大学发音词典，用于文本转音素 (G2P)"
    },
    {
        "id": "averaged_perceptron_tagger",
        "name": "Averaged Perceptron Tagger",
        "path": "taggers/averaged_perceptron_tagger",
        "description": "词性标注器，用于辅助发音预测"
    }
]

class NLTKManager:
    def __init__(self):
        self.data_dir = Config.NLTK_DATA_DIR
        self._ensure_data_dir()
        
        # 配置 NLTK 搜索路径
        if str(self.data_dir) not in nltk.data.path:
            nltk.data.path.append(str(self.data_dir))
            
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
    def get_status(self) -> Dict[str, Any]:
        """获取 NLTK 资源状态"""
        resources = []
        all_installed = True
        
        for res in REQUIRED_RESOURCES:
            installed = self._check_resource(res["path"])
            if not installed:
                all_installed = False
                
            resources.append({
                "id": res["id"],
                "name": res["name"],
                "description": res["description"],
                "installed": installed
            })
            
        return {
            "installed": all_installed,
            "resources": resources,
            "data_dir": str(self.data_dir)
        }
        
    def _check_resource(self, resource_path: str) -> bool:
        """检查资源是否已安装"""
        try:
            nltk.data.find(resource_path)
            return True
        except LookupError:
            return False
            
    def download_resource(self, resource_id: str) -> bool:
        """下载指定资源"""
        try:
            logger.info(f"Downloading NLTK resource: {resource_id} to {self.data_dir}")
            nltk.download(resource_id, download_dir=str(self.data_dir), quiet=True)
            return True
        except Exception as e:
            logger.error(f"Failed to download NLTK resource {resource_id}: {e}")
            raise e

    def download_all(self):
        """下载所有必需资源"""
        for res in REQUIRED_RESOURCES:
            if not self._check_resource(res["path"]):
                self.download_resource(res["id"])

# 单例模式
_manager: Optional[NLTKManager] = None

def get_nltk_manager() -> NLTKManager:
    global _manager
    if _manager is None:
        _manager = NLTKManager()
    return _manager
