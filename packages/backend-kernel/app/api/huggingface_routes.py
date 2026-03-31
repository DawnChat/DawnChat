"""
DawnChat - HuggingFace 模型市场 API

提供从 HuggingFace 获取模型列表、搜索和下载功能。
默认数据源: lmstudio-community (开放，无需认证)

设计兼容多数据源，便于将来扩展。
支持镜像地址: hf-mirror.com

下载文件命名规范：
- 下载中: filename.gguf.downloading
- 下载元信息: filename.gguf.download_meta (JSON，用于断点续传)
- 下载完成: filename.gguf
- manifest.json 记录所有已下载模型的元信息

断点续传支持：
- 使用 HTTP Range 请求从已下载位置继续
- .download_meta 文件保存下载状态和进度
- 暂停时保留 .downloading 和 .download_meta 文件
- 取消时删除所有临时文件
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import importlib
import json
import os
from pathlib import Path
import threading
from typing import Any, AsyncIterator, Dict, List, Optional, cast
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import Config
from app.services.hf_download_v2 import REPO_DOWNLOAD_MARKER, get_hf_download_manager_v2
from app.utils.logger import api_logger as logger

# ============ 下载状态枚举 ============

class DownloadStatus(str, Enum):
    """下载状态"""
    PENDING = "pending"          # 等待开始
    DOWNLOADING = "downloading"  # 下载中
    PAUSED = "paused"           # 已暂停（可恢复）
    COMPLETED = "completed"      # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"      # 已取消


@dataclass
class DownloadMeta:
    """
    下载元信息 - 用于断点续传
    
    保存到 .download_meta 文件，App 重启后可恢复下载
    """
    model_id: str               # HuggingFace 模型 ID
    filename: str               # 文件名
    download_url: str           # 下载 URL
    save_path: str              # 最终保存路径
    total_bytes: int            # 文件总大小
    downloaded_bytes: int       # 已下载字节数
    status: str                 # 下载状态
    use_mirror: bool            # 是否使用镜像
    started_at: str             # 开始时间
    updated_at: str             # 更新时间
    error_message: Optional[str] = None  # 错误信息
    parameters: Optional[str] = None  # 参数量
    capabilities: Optional[List[str]] = None  # 能力
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DownloadMeta':
        """从字典创建"""
        return cls(
            model_id=data.get("model_id", ""),
            filename=data.get("filename", ""),
            download_url=data.get("download_url", ""),
            save_path=data.get("save_path", ""),
            total_bytes=data.get("total_bytes", 0),
            downloaded_bytes=data.get("downloaded_bytes", 0),
            status=data.get("status", DownloadStatus.PENDING),
            use_mirror=data.get("use_mirror", True),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            error_message=data.get("error_message"),
            parameters=data.get("parameters"),
            capabilities=data.get("capabilities")
        )
    
    def save(self, meta_path: Path):
        """保存到文件"""
        self.updated_at = datetime.now().isoformat()
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, meta_path: Path) -> Optional['DownloadMeta']:
        """从文件加载"""
        try:
            if meta_path.exists():
                with open(meta_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"加载下载元信息失败: {meta_path}, 错误: {e}")
        return None


def get_meta_path(save_path: Path) -> Path:
    """获取元信息文件路径"""
    return Path(str(save_path) + ".download_meta")


def get_downloading_path(save_path: Path) -> Path:
    """获取下载中文件路径"""
    return Path(str(save_path) + ".downloading")


# 创建路由器
router = APIRouter(prefix="/huggingface", tags=["HuggingFace Models"])


# ============ Manifest 管理 ============

MANIFEST_FILE = Config.MODELS_DIR / "manifest.json"
_manifest_lock = threading.Lock()


def load_manifest() -> dict:
    """加载 manifest.json"""
    with _manifest_lock:
        if MANIFEST_FILE.exists():
            try:
                with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载 manifest 失败: {e}")
        return {"version": 1, "models": {}}


def save_manifest(manifest: dict):
    """保存 manifest.json"""
    with _manifest_lock:
        try:
            MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            logger.info("✅ 已更新 manifest.json")
        except Exception as e:
            logger.error(f"保存 manifest 失败: {e}")


def detect_model_format_from_filename(filename: str) -> Optional[str]:
    lower = filename.lower()
    if lower.endswith(".gguf"):
        return "gguf"
    if lower.endswith(".safetensors") or "mlx" in lower:
        return "mlx"
    return None


def add_model_to_manifest(
    model_id: str,
    filename: str,
    save_path: Path,
    file_size: int,
    parameters: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
    model_format: Optional[str] = None
):
    """添加模型到 manifest"""
    manifest = load_manifest()
    
    # 使用 model_id/filename 作为唯一键
    key = f"{model_id}/{filename}"
    
    model_data = {
        "model_id": model_id,
        "filename": filename,
        "path": str(save_path),
        "relative_path": str(save_path.relative_to(Config.MODELS_DIR)),
        "size": file_size,
        "downloaded_at": datetime.now().isoformat(),
        "author": model_id.split('/')[0] if '/' in model_id else "unknown",
    }

    # 只有当值不为 None 时才添加，避免覆盖已有的信息（如果已有且当前为None）
    # 但这里是下载完成，通常是最新的信息。
    if parameters:
        model_data["parameters"] = parameters
    if capabilities:
        model_data["capabilities"] = capabilities
    resolved_format = model_format or detect_model_format_from_filename(filename)
    if resolved_format:
        model_data["format"] = resolved_format
        
    manifest["models"][key] = model_data
    
    save_manifest(manifest)


def remove_model_from_manifest(model_id: str, filename: str):
    """从 manifest 移除模型"""
    manifest = load_manifest()
    key = f"{model_id}/{filename}"
    
    if key in manifest.get("models", {}):
        del manifest["models"][key]
        save_manifest(manifest)
        return True
    return False


# ============ 常量 ============

HUGGINGFACE_API = "https://huggingface.co/api"
HUGGINGFACE_MIRROR_API = "https://hf-mirror.com/api"
HUGGINGFACE_DOWNLOAD = "https://huggingface.co"
HUGGINGFACE_MIRROR_DOWNLOAD = "https://hf-mirror.com"
DEFAULT_AUTHOR = "lmstudio-community,mlx-community,onnx-community,Qwen"
PAGE_SIZE = 20


# ============ MMProj (视觉模型投影层) 辅助函数 ============

def is_mmproj_file(filename: str) -> bool:
    """
    判断是否为 mmproj 文件（视觉模型的投影层文件）
    
    Args:
        filename: 文件名
    
    Returns:
        是否为 mmproj 文件
    """
    lower = filename.lower()
    return 'mmproj' in lower or 'mm-proj' in lower


def find_mmproj_file(files: List[dict]) -> Optional[str]:
    """
    从文件列表中查找 mmproj 文件
    
    Args:
        files: 文件列表 (来自 HuggingFace API)
    
    Returns:
        mmproj 文件名，如果没有则返回 None
    """
    for f in files:
        filename = f.get("rfilename", "")
        if is_mmproj_file(filename) and filename.lower().endswith('.gguf'):
            return filename
    return None


def is_mmproj_downloaded(model_id: str, mmproj_filename: str) -> bool:
    """
    检查 mmproj 文件是否已下载
    
    Args:
        model_id: 模型 ID
        mmproj_filename: mmproj 文件名
    
    Returns:
        是否已下载
    """
    save_path = get_model_storage_path(model_id, mmproj_filename)
    return save_path.exists()


# ============ 请求/响应模型 ============

class DownloadRequest(BaseModel):
    """下载请求"""
    model_id: str      # e.g. "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    filename: str      # e.g. "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    use_mirror: Optional[bool] = None  # 是否使用镜像，None 时按策略自动选择
    resume: bool = False     # 是否为恢复下载（断点续传）
    parameters: Optional[str] = None  # 参数量，e.g. "7B"
    capabilities: Optional[List[str]] = None  # 能力，e.g. ["text", "vision"]


class CancelDownloadRequest(BaseModel):
    """取消下载请求"""
    model_id: str
    filename: str


class PauseDownloadRequest(BaseModel):
    """暂停下载请求"""
    model_id: str
    filename: str


# ============ 工具函数 ============

def get_model_dir_hash(model_id: str) -> str:
    """
    为模型 ID 生成短哈希，用于创建唯一的存储目录
    
    Args:
        model_id: 模型 ID (e.g. "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
    
    Returns:
        8 位 hash 字符串
    """
    return hashlib.sha256(model_id.encode()).hexdigest()[:8]


def get_model_storage_dir(model_id: str) -> Path:
    """
    获取模型存储目录
    
    结构: models/{author}/{model_name}_{hash}
    """
    parts = model_id.split('/')
    if len(parts) >= 2:
        author = parts[0]
        model_name = '/'.join(parts[1:])
    else:
        author = "unknown"
        model_name = model_id
    
    hash_suffix = get_model_dir_hash(model_id)
    dir_name = f"{model_name}_{hash_suffix}"
    
    return Config.MODELS_DIR / author / dir_name


def get_model_storage_path(model_id: str, filename: str) -> Path:
    """
    获取模型文件的存储路径
    
    结构: models/{author}/{model_name}_{hash}/{filename}
    例如: models/lmstudio-community/Qwen2.5-7B-Instruct-GGUF_a1b2c3d4/Qwen2.5-7B-Instruct-Q4_K_M.gguf
    
    Args:
        model_id: 模型 ID
        filename: 文件名
    
    Returns:
        完整的存储路径
    """
    return get_model_storage_dir(model_id) / filename


# ============ 下载任务管理 ============

# 取消标记：True = 取消（删除文件），False = 正常
_cancel_requests: dict[str, bool] = {}

# 暂停标记：True = 暂停（保留文件）
_pause_requests: dict[str, bool] = {}

# 当前活跃的下载任务（用于检查是否有下载正在进行）
_active_downloads: dict[str, bool] = {}


def get_task_id(model_id: str, filename: str) -> str:
    """生成任务 ID"""
    return f"{model_id}/{filename}"


def request_cancel(model_id: str, filename: str) -> bool:
    """请求取消下载（会删除临时文件）"""
    task_id = get_task_id(model_id, filename)
    _cancel_requests[task_id] = True
    # 如果有暂停请求，也清除
    _pause_requests.pop(task_id, None)
    return True


def request_pause(model_id: str, filename: str) -> bool:
    """请求暂停下载（保留临时文件用于续传）"""
    task_id = get_task_id(model_id, filename)
    # 只有正在下载的任务才能暂停
    if not _active_downloads.get(task_id, False):
        return False
    _pause_requests[task_id] = True
    return True


def is_cancel_requested(model_id: str, filename: str) -> bool:
    """检查是否请求取消"""
    task_id = get_task_id(model_id, filename)
    return _cancel_requests.get(task_id, False)


def is_pause_requested(model_id: str, filename: str) -> bool:
    """检查是否请求暂停"""
    task_id = get_task_id(model_id, filename)
    return _pause_requests.get(task_id, False)


def clear_cancel_request(model_id: str, filename: str):
    """清除取消请求"""
    task_id = get_task_id(model_id, filename)
    _cancel_requests.pop(task_id, None)


def clear_pause_request(model_id: str, filename: str):
    """清除暂停请求"""
    task_id = get_task_id(model_id, filename)
    _pause_requests.pop(task_id, None)


def set_download_active(model_id: str, filename: str, active: bool):
    """设置下载是否活跃"""
    task_id = get_task_id(model_id, filename)
    if active:
        _active_downloads[task_id] = True
    else:
        _active_downloads.pop(task_id, None)


def is_download_active(model_id: str, filename: str) -> bool:
    """检查下载是否活跃"""
    task_id = get_task_id(model_id, filename)
    return _active_downloads.get(task_id, False)


# ============ HuggingFace API 调用 ============

def get_api_base(use_mirror: bool = True) -> str:
    """获取 API 基础 URL"""
    return HUGGINGFACE_MIRROR_API if use_mirror else HUGGINGFACE_API


def get_download_base(use_mirror: bool = True) -> str:
    """获取下载基础 URL"""
    return HUGGINGFACE_MIRROR_DOWNLOAD if use_mirror else HUGGINGFACE_DOWNLOAD


def get_hf_endpoint(use_mirror: Optional[bool] = None) -> str:
    """获取 HuggingFace Hub endpoint"""
    if use_mirror is True:
        return "https://hf-mirror.com"
    if use_mirror is False:
        return "https://huggingface.co"
    return os.getenv("HF_ENDPOINT", "https://huggingface.co")


def _normalize_author_list(source: str) -> List[str]:
    if not source:
        return []
    return [s.strip() for s in source.split(",") if s.strip()]


def _normalize_format_list(formats: Optional[str]) -> List[str]:
    if not formats:
        return []
    normalized = [f.strip().lower() for f in formats.split(",") if f.strip()]
    return [f for f in normalized if f in ("gguf", "mlx")]


def _detect_model_format_from_info(model_info: dict) -> Optional[str]:
    model_id = (model_info.get("id") or "").lower()
    tags = [str(t).lower() for t in model_info.get("tags", [])]
    library_name = (model_info.get("library_name") or "").lower()
    if "gguf" in tags or "gguf" in model_id:
        return "gguf"
    if "mlx" in tags or "mlx" in library_name or "mlx" in model_id:
        return "mlx"
    return None


def fetch_models_from_huggingface(
    author: str = DEFAULT_AUTHOR,
    search: str = "",
    page: int = 0,
    limit: int = PAGE_SIZE,
    use_mirror: bool = True,
    formats: Optional[List[str]] = None
) -> List[dict]:
    """
    从 HuggingFace API 获取模型列表（使用官方 huggingface_hub 库）
    
    Args:
        author: 作者/组织名称
        search: 搜索关键词
        page: 页码
        limit: 每页数量
        use_mirror: 是否使用镜像
    
    Returns:
        模型列表
    """
    from huggingface_hub import HfApi
    
    try:
        endpoint = get_hf_endpoint(use_mirror)
        api = HfApi(endpoint=endpoint)
        
        logger.info(f"🔍 使用 HfApi 搜索模型: author={author}, search={search}, page={page}, 镜像: {use_mirror}")
        
        # 计算需要获取的总数量：需要获取到第 page 页的数据
        # huggingface_hub 的 list_models 没有 offset 参数，只能通过 limit 获取前 N 个
        fetch_limit = (page + 1) * limit
        
        author_list = _normalize_author_list(author)
        if not author_list:
            author_list = [DEFAULT_AUTHOR]

        filter_value = None
        if formats and len(formats) == 1:
            filter_value = formats[0]

        all_models = []
        for author_item in author_list:
            models_iter = api.list_models(
                author=author_item,
                search=search if search else None,
                filter=filter_value,
                sort="downloads",
                limit=fetch_limit,
            )
            all_models.extend(list(models_iter))

        unique_models = {}
        for model in all_models:
            unique_models[model.id] = model
        all_models = list(unique_models.values())

        all_models.sort(
            key=lambda m: getattr(m, "downloads", 0) or 0,
            reverse=True
        )

        start_idx = page * limit
        end_idx = start_idx + limit
        page_models = all_models[start_idx:end_idx]

        result = []
        for model in page_models:
            model_info = {
                "id": model.id,
                "modelId": model.id,
                "author": getattr(model, "author", None),
                "downloads": getattr(model, "downloads", 0) or 0,
                "likes": getattr(model, "likes", 0) or 0,
                "lastModified": getattr(model, "last_modified", None),
                "tags": getattr(model, "tags", []) or [],
                "private": getattr(model, "private", False),
                "pipeline_tag": getattr(model, "pipeline_tag", None),
                "library_name": getattr(model, "library_name", None),
                "sha": getattr(model, "sha", None),
            }
            model_info["format"] = _detect_model_format_from_info(model_info)
            result.append(model_info)

        if formats:
            result = [
                m for m in result
                if m.get("format") in formats
            ]
        
        logger.info(f"✅ 获取到 {len(result)} 个模型")
        return result
        
    except Exception as e:
        logger.error(f"❌ HuggingFace API 请求失败: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"HuggingFace API 请求失败: {str(e)}"
        )


def fetch_model_files(model_id: str, use_mirror: bool = True) -> List[dict]:
    """
    获取模型的文件列表（使用官方 huggingface_hub 库，包含文件大小）
    
    Args:
        model_id: 模型 ID
        use_mirror: 是否使用镜像
    
    Returns:
        文件列表（包含文件大小）
    """
    from huggingface_hub import HfApi
    
    try:
        endpoint = get_hf_endpoint(use_mirror)
        api = HfApi(endpoint=endpoint)
        
        logger.info(f"📂 使用 HfApi 获取模型文件: {model_id}, 镜像: {use_mirror}")
        
        # 使用 model_info 获取文件信息（必须 files_metadata=True 才能获取文件大小）
        model_info = api.model_info(
            repo_id=model_id,
            files_metadata=True  # 关键：必须传入才能获取文件大小
        )
        
        # 转换为字典格式
        siblings = []
        for f in model_info.siblings or []:
            siblings.append({
                "rfilename": f.rfilename,
                "size": getattr(f, 'size', None),  # 现在可以获取文件大小了
                "lfs": getattr(f, 'lfs', None),
            })
        
        logger.info(f"✅ 模型 {model_id} 共有 {len(siblings)} 个文件")
        return siblings
        
    except Exception as e:
        logger.error(f"❌ 获取模型文件失败: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"获取模型文件失败: {str(e)}"
        )


def fetch_model_info(model_id: str, use_mirror: bool = True) -> dict:
    """
    获取模型详细信息（使用官方 huggingface_hub 库）
    
    Args:
        model_id: 模型 ID
        use_mirror: 是否使用镜像
    
    Returns:
        模型详细信息字典
    """
    from huggingface_hub import HfApi
    
    try:
        endpoint = get_hf_endpoint(use_mirror)
        api = HfApi(endpoint=endpoint)
        
        logger.info(f"ℹ️ 使用 HfApi 获取模型信息: {model_id}, 镜像: {use_mirror}")
        
        # 使用 model_info 获取详细信息（包含文件大小）
        info = api.model_info(
            repo_id=model_id,
            files_metadata=True
        )
        
        # 转换为字典格式
        result = {
            "id": info.id,
            "modelId": info.id,
            "author": info.author,
            "downloads": getattr(info, 'downloads', 0),
            "likes": getattr(info, 'likes', 0),
            "lastModified": getattr(info, 'last_modified', None),
            "tags": getattr(info, 'tags', []),
            "private": getattr(info, 'private', False),
            "siblings": [
                {
                    "rfilename": f.rfilename,
                    "size": getattr(f, 'size', None),
                    "lfs": getattr(f, 'lfs', None),
                }
                for f in info.siblings
            ] if info.siblings else []
        }
        
        logger.info(f"✅ 获取到模型信息: {model_id}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 获取模型信息失败: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"获取模型信息失败: {str(e)}"
        )


async def download_file_with_progress(
    model_id: str,
    filename: str,
    save_path: Path,
    use_mirror: bool = True,
    resume: bool = False,
    parameters: Optional[str] = None,
    capabilities: Optional[List[str]] = None
) -> AsyncIterator[dict]:
    """
    [已废弃] 下载文件并返回进度（支持断点续传）
    
    注意：此函数已废弃，新下载请使用 hf_download_manager.download_single_file。
    保留此函数仅用于向后兼容（旧版 mmproj 下载）。
    
    下载命名规范：
    - 下载中: filename.gguf.downloading
    - 下载元信息: filename.gguf.download_meta
    - 下载完成: filename.gguf
    
    断点续传：
    - 如果 resume=True 且存在 .download_meta，从已下载位置继续
    - 使用 HTTP Range 请求实现
    
    Args:
        model_id: 模型 ID
        filename: 文件名
        save_path: 保存路径（最终路径，不含 .downloading）
        use_mirror: 是否使用镜像
        resume: 是否为恢复下载
        parameters: 模型参数量
        capabilities: 模型能力列表
    
    Yields:
        进度信息字典
    """
    # 构建下载 URL
    download_base = get_download_base(use_mirror)
    download_url = f"{download_base}/{model_id}/resolve/main/{quote(filename)}"
    
    task_id = get_task_id(model_id, filename)
    logger.info(f"⬇️ {'恢复' if resume else '开始'}下载任务 [{task_id}]: {download_url}")
    logger.info(f"📁 保存路径: {save_path}")
    logger.info(f"🌐 使用镜像: {use_mirror}")
    
    # 确保目录存在
    save_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 临时文件路径
    downloading_path = get_downloading_path(save_path)
    meta_path = get_meta_path(save_path)
    
    # 检查是否需要断点续传
    start_byte = 0
    existing_meta: Optional[DownloadMeta] = None
    
    if resume and meta_path.exists():
        existing_meta = DownloadMeta.load(meta_path)
        if existing_meta and downloading_path.exists():
            # 验证文件大小与记录是否一致
            actual_size = downloading_path.stat().st_size
            if actual_size == existing_meta.downloaded_bytes:
                start_byte = actual_size
                logger.info(f"📂 发现已下载 {start_byte} 字节，将从此处续传")
            else:
                logger.warning(f"文件大小不匹配: 实际 {actual_size}, 记录 {existing_meta.downloaded_bytes}")
                start_byte = actual_size  # 使用实际大小
    
    # 标记下载为活跃状态
    set_download_active(model_id, filename, True)
    
    try:
        # 初始进度
        yield {
            "status": "downloading",
            "total": existing_meta.total_bytes if existing_meta else 0,
            "completed": start_byte,
            "progress": 0,
            "task_id": task_id,
            "resuming": start_byte > 0
        }
        
        # 使用独立的进度数据字典（每个任务独立）
        progress_data: Dict[str, Any] = {
            "downloaded": start_byte, 
            "total": existing_meta.total_bytes if existing_meta else 0, 
            "done": False, 
            "error": None,
            "paused": False,
            "speed": 0,
            "last_time": datetime.now(),
            "last_bytes": start_byte
        }
        
        def download_thread():
            """下载线程 - 支持断点续传"""
            nonlocal progress_data
            try:
                # 构建请求头（支持 Range 请求）
                headers = {}
                if start_byte > 0:
                    headers["Range"] = f"bytes={start_byte}-"
                    logger.info(f"📡 使用 Range 请求: bytes={start_byte}-")
                
                # 设置较长的超时时间，模型文件可能很大
                requests = importlib.import_module("requests")
                with requests.get(download_url, stream=True, timeout=(30, 300), headers=headers) as response:
                    # 检查响应状态
                    if response.status_code == 416:
                        # Range Not Satisfiable - 文件可能已完整
                        logger.info("服务器返回 416，文件可能已完整下载")
                        progress_data["done"] = True
                        return
                    
                    response.raise_for_status()
                    
                    # 获取文件总大小
                    if start_byte > 0 and response.status_code == 206:
                        # 部分内容响应，从 Content-Range 获取总大小
                        content_range = response.headers.get('Content-Range', '')
                        if '/' in content_range:
                            progress_data["total"] = int(content_range.split('/')[-1])
                        else:
                            # 如果没有 Content-Range，使用 existing_meta 中的值
                            if existing_meta:
                                progress_data["total"] = existing_meta.total_bytes
                    else:
                        # 新下载
                        progress_data["total"] = int(response.headers.get('content-length', 0)) + start_byte
                    
                    # 创建或更新元信息
                    meta = DownloadMeta(
                        model_id=model_id,
                        filename=filename,
                        download_url=download_url,
                        save_path=str(save_path),
                        total_bytes=progress_data["total"],
                        downloaded_bytes=start_byte,
                        status=DownloadStatus.DOWNLOADING,
                        use_mirror=use_mirror,
                        started_at=existing_meta.started_at if existing_meta else datetime.now().isoformat(),
                        updated_at=datetime.now().isoformat(),
                        parameters=parameters or (existing_meta.parameters if existing_meta else None),
                        capabilities=capabilities or (existing_meta.capabilities if existing_meta else None)
                    )
                    meta.save(meta_path)
                    
                    # 打开文件（追加模式如果是续传）
                    mode = 'ab' if start_byte > 0 else 'wb'
                    with open(downloading_path, mode) as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                            # 检查暂停请求
                            if is_pause_requested(model_id, filename):
                                logger.info(f"⏸️ 收到暂停请求 [{task_id}]")
                                progress_data["paused"] = True
                                # 更新元信息为暂停状态
                                meta.downloaded_bytes = progress_data["downloaded"]
                                meta.status = DownloadStatus.PAUSED
                                meta.save(meta_path)
                                return
                            
                            # 检查取消请求
                            if is_cancel_requested(model_id, filename):
                                progress_data["error"] = "下载已取消"
                                return
                            
                            if chunk:
                                f.write(chunk)
                                progress_data["downloaded"] += len(chunk)
                                
                                # 计算下载速度
                                now = datetime.now()
                                elapsed = (now - progress_data["last_time"]).total_seconds()
                                if elapsed >= 1.0:
                                    bytes_diff = progress_data["downloaded"] - progress_data["last_bytes"]
                                    progress_data["speed"] = bytes_diff / elapsed
                                    progress_data["last_time"] = now
                                    progress_data["last_bytes"] = progress_data["downloaded"]
                                    
                                    # 定期更新元信息（每秒一次）
                                    meta.downloaded_bytes = progress_data["downloaded"]
                                    meta.save(meta_path)
                
                progress_data["done"] = True
            except Exception as e:
                progress_data["error"] = str(e)
        
        # 创建独立的下载线程
        thread = threading.Thread(target=download_thread, name=f"download-{task_id}")
        thread.start()
        
        # 轮询进度
        last_downloaded = start_byte
        while thread.is_alive():
            await asyncio.sleep(0.5)  # 每 0.5 秒更新一次
            
            # 检查错误或暂停
            if progress_data["error"] or progress_data["paused"]:
                break
            
            # 发送进度更新
            downloaded = cast(int, progress_data["downloaded"])
            total = cast(int, progress_data["total"])
            if downloaded >= last_downloaded:
                last_downloaded = downloaded
                
                yield {
                    "status": "downloading",
                    "total": total,
                    "completed": downloaded,
                    "progress": (downloaded / total * 100) if total > 0 else 0,
                    "speed": progress_data["speed"],
                    "task_id": task_id
                }
        
        thread.join()
        total = cast(int, progress_data["total"])
        downloaded = cast(int, progress_data["downloaded"])
        
        # 检查暂停
        if progress_data["paused"]:
            yield {
                "status": "paused",
                "total": total,
                "completed": downloaded,
                "progress": (downloaded / total * 100) if total > 0 else 0,
                "message": "下载已暂停，可随时恢复",
                "task_id": task_id
            }
            return
        
        # 检查错误
        if progress_data["error"]:
            raise Exception(progress_data["error"])
        
        if not progress_data["done"]:
            raise Exception("下载未完成")
        
        # 下载完成，重命名文件
        if downloading_path.exists():
            downloading_path.rename(save_path)
            logger.info(f"✅ 下载完成 [{task_id}]: {save_path}")
            
            # 删除元信息文件
            if meta_path.exists():
                meta_path.unlink()
            
            # 添加到 manifest
            add_model_to_manifest(
                model_id, 
                filename, 
                save_path, 
                total,
                parameters=parameters or (existing_meta.parameters if existing_meta else None),
                capabilities=capabilities or (existing_meta.capabilities if existing_meta else None)
            )
        
        yield {
            "status": "success",
            "total": total,
            "completed": total,
            "progress": 100,
            "message": "下载完成",
            "path": str(save_path),
            "task_id": task_id
        }
        
    except Exception as e:
        error_msg = str(e)
        is_cancelled = "取消" in error_msg
        
        logger.error(f"❌ 下载失败 [{task_id}]: {e}")
        
        if is_cancelled:
            # 取消时删除所有临时文件
            if downloading_path.exists():
                try:
                    downloading_path.unlink()
                    logger.info(f"🗑️ 已清理临时文件: {downloading_path}")
                except Exception as cleanup_error:
                    logger.warning(f"清理临时文件失败: {cleanup_error}")
            
            if meta_path.exists():
                try:
                    meta_path.unlink()
                    logger.info(f"🗑️ 已清理元信息文件: {meta_path}")
                except Exception as cleanup_error:
                    logger.warning(f"清理元信息文件失败: {cleanup_error}")
            
            yield {
                "status": "cancelled",
                "message": "下载已取消",
                "task_id": task_id
            }
        else:
            # 其他错误，更新元信息但保留文件（方便后续重试）
            if meta_path.exists():
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.FAILED
                    meta.error_message = error_msg
                    meta.save(meta_path)
            
            yield {
                "status": "error",
                "message": error_msg,
                "task_id": task_id
            }
    
    finally:
        # 清理请求标记
        clear_cancel_request(model_id, filename)
        clear_pause_request(model_id, filename)
        set_download_active(model_id, filename, False)


# ============ API 路由 ============

@router.get("/models")
async def list_models(
    page: int = Query(0, ge=0),
    search: str = Query(""),
    source: str = Query(DEFAULT_AUTHOR),
    use_mirror: str = Query("true"),
    formats: str = Query("")
):
    """
    获取模型列表
    
    Args:
        page: 页码 (从 0 开始)
        search: 搜索关键词
        source: 数据源/作者 (默认 lmstudio-community)
        use_mirror: 是否使用镜像 ("true"/"false")
    
    Returns:
        模型列表
    """
    try:
        mirror = use_mirror.lower() == "true"
        format_list = _normalize_format_list(formats)
        models = fetch_models_from_huggingface(
            author=source,
            search=search,
            page=page,
            use_mirror=mirror,
            formats=format_list
        )
        
        # 转换格式
        result = []
        for model in models:
            result.append({
                "id": model.get("id", ""),
                "modelId": model.get("modelId", ""),
                "author": model.get("author", source),
                "sha": model.get("sha", ""),
                "lastModified": model.get("lastModified", ""),
                "private": model.get("private", False),
                "disabled": model.get("disabled", False),
                "gated": model.get("gated", False),
                "downloads": model.get("downloads", 0),
                "likes": model.get("likes", 0),
                "tags": model.get("tags", []),
                "pipeline_tag": model.get("pipeline_tag"),
                "library_name": model.get("library_name"),
                "format": model.get("format")
            })
        
        return {
            "status": "success",
            "page": page,
            "count": len(result),
            "models": result,
            "use_mirror": mirror
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id:path}/info")
async def get_model_info(
    model_id: str,
    use_mirror: str = Query("true")
):
    """
    获取模型详细信息
    
    Args:
        model_id: 模型 ID (e.g. "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        use_mirror: 是否使用镜像
    
    Returns:
        模型详细信息
    """
    try:
        mirror = use_mirror.lower() == "true"
        info = fetch_model_info(model_id, use_mirror=mirror)
        
        return {
            "status": "success",
            "model": info,
            "use_mirror": mirror
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{model_id:path}/files")
async def get_model_files(
    model_id: str,
    use_mirror: str = Query("true")
):
    """
    获取模型的文件列表
    
    Args:
        model_id: 模型 ID (e.g. "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        use_mirror: 是否使用镜像
    
    Returns:
        文件列表
    """
    try:
        mirror = use_mirror.lower() == "true"
        files = fetch_model_files(model_id, use_mirror=mirror)
        
        all_files = []
        for f in files:
            filename = f.get("rfilename", "")
            all_files.append({
                "rfilename": filename,
                "size": f.get("size"),
                "lfs": f.get("lfs")
            })
        
        return {
            "status": "success",
            "model_id": model_id,
            "count": len(all_files),
            "files": all_files,
            "use_mirror": mirror
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型文件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def download_mmproj_if_needed(
    model_id: str,
    use_mirror: bool,
    parameters: Optional[str] = None,
    capabilities: Optional[List[str]] = None
) -> AsyncIterator[dict]:
    """
    [已废弃] 检测并下载 mmproj 文件（如果需要）
    
    注意：此函数已废弃，使用 _download_mmproj_background 代替。
    保留此函数仅用于向后兼容。
    
    用于视觉模型，在主模型下载完成后自动下载配套的 mmproj 文件。
    
    Args:
        model_id: 模型 ID
        use_mirror: 是否使用镜像
        parameters: 模型参数量
        capabilities: 模型能力列表
    
    Yields:
        下载进度信息
    """
    try:
        # 获取模型文件列表
        files = fetch_model_files(model_id, use_mirror=use_mirror)
        
        # 查找 mmproj 文件
        mmproj_filename = find_mmproj_file(files)
        
        if not mmproj_filename:
            logger.info(f"📷 模型 {model_id} 没有 mmproj 文件")
            return
        
        # 检查是否已下载
        if is_mmproj_downloaded(model_id, mmproj_filename):
            logger.info(f"📷 mmproj 文件已存在: {mmproj_filename}")
            yield {
                "status": "mmproj_exists",
                "mmproj_filename": mmproj_filename,
                "message": "视觉投影文件已存在"
            }
            return
        
        logger.info(f"📷 检测到 mmproj 文件需要下载: {mmproj_filename}")
        
        # 通知前端开始下载 mmproj
        yield {
            "status": "mmproj_starting",
            "mmproj_filename": mmproj_filename,
            "message": "开始下载视觉投影文件"
        }
        
        # 下载 mmproj 文件
        mmproj_save_path = get_model_storage_path(model_id, mmproj_filename)
        
        async for progress in download_file_with_progress(
            model_id,
            mmproj_filename,
            mmproj_save_path,
            use_mirror=use_mirror,
            resume=False,
            parameters=parameters,
            capabilities=capabilities
        ):
            # 标记为 mmproj 相关的进度
            progress["is_mmproj"] = True
            progress["mmproj_filename"] = mmproj_filename
            yield progress
            
    except Exception as e:
        logger.error(f"下载 mmproj 文件失败: {e}", exc_info=True)
        yield {
            "status": "mmproj_error",
            "message": f"下载视觉投影文件失败: {str(e)}"
        }


def get_llm_task_id(model_id: str, filename: str) -> str:
    """生成 LLM 下载任务 ID（用于 hf_download_manager）"""
    # 使用简化的 ID，去掉特殊字符
    return f"{model_id}_{filename}".replace("/", "_")


async def on_llm_download_complete(model_type: str, model_id: str):
    """
    LLM 模型下载完成回调
    
    用于添加模型到 manifest，以及触发 mmproj 下载
    """
    logger.info(f"📞 LLM 下载完成回调: {model_type} / {model_id}")
    # 回调中的 model_id 是 task_id 格式，需要解析
    # 格式: "{hf_repo_id}_{filename}".replace("/", "_")
    # 这里的处理将在下载完成后的 manifest 更新中执行
    pass


@router.post("/download")
async def download_model(request: DownloadRequest):
    """
    下载模型文件（后台任务 + 轮询模式）
    
    使用 HFDownloadManagerV2 进行下载，通过文件大小轮询跟踪进度。
    通过 GET /download/progress/{model_id}?filename=xxx 查询进度。
    
    支持并行下载多个模型，每个下载任务独立运行。
    
    对于视觉模型（含 mmproj 文件）：
    - 主模型下载完成后自动检测并下载 mmproj 文件
    - mmproj 文件存储在与主模型相同的目录
    
    Args:
        request: 下载请求
    
    Returns:
        启动状态，后续通过轮询获取进度
    """
    try:
        model_id = request.model_id
        filename = request.filename
        use_mirror = bool(request.use_mirror)
        task_id = get_task_id(model_id, filename)
        llm_task_id = get_llm_task_id(model_id, filename)
        
        logger.info(f"📥 收到下载请求 [{task_id}], 镜像: {use_mirror}")
        
        is_repo_download = filename == REPO_DOWNLOAD_MARKER
        manager = get_hf_download_manager_v2()
        
        if is_repo_download:
            save_dir = get_model_storage_dir(model_id)
            if save_dir.exists() and any(save_dir.iterdir()):
                progress = manager.get_progress("llm", llm_task_id)
                status = progress.get("status")
                if status not in ["failed", "paused", "cancelled"]:
                    raise HTTPException(
                        status_code=400,
                        detail=f"仓库已存在: {save_dir}"
                    )
            
            if manager.is_active("llm", llm_task_id):
                raise HTTPException(
                    status_code=400,
                    detail="该仓库正在下载中"
                )
            
            async def on_complete(model_type: str, task_id: str):
                logger.info(f"📞 LLM 仓库下载完成: {model_id}")
                if save_dir.exists():
                    for file_path in save_dir.rglob("*"):
                        if not file_path.is_file():
                            continue
                        lower_name = file_path.name.lower()
                        if lower_name.endswith(".gguf") or lower_name.endswith(".safetensors"):
                            add_model_to_manifest(
                                model_id,
                                file_path.name,
                                file_path,
                                file_path.stat().st_size,
                                parameters=request.parameters,
                                capabilities=request.capabilities
                            )
            
            result = await manager.start_download(
                model_type="llm",
                model_id=llm_task_id,
                hf_repo_id=model_id,
                save_dir=save_dir,
                filename=REPO_DOWNLOAD_MARKER,
                use_mirror=use_mirror,
                parameters=request.parameters,
                capabilities=request.capabilities,
                on_complete=on_complete
            )
            
            if result.get("status") == "error":
                raise HTTPException(
                    status_code=400,
                    detail=result.get("message", "启动下载失败")
                )
            
            return {
                "status": "started",
                "message": "仓库下载任务已启动，请通过进度接口查询状态",
                "task_id": llm_task_id,
                "model_id": model_id,
                "filename": filename,
                "progress_url": f"/huggingface/download/progress/{model_id}?filename={filename}"
            }
        
        save_path = get_model_storage_path(model_id, filename)
        save_dir = save_path.parent
        
        if save_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"文件已存在: {save_path}"
            )
        
        if manager.is_active("llm", llm_task_id):
            raise HTTPException(
                status_code=400,
                detail="该文件正在下载中"
            )
        
        # 判断是否为 mmproj 文件
        is_mmproj = is_mmproj_file(filename)
        
        # 下载完成后的回调：添加到 manifest 并检测 mmproj
        async def on_complete(model_type: str, task_id: str):
            logger.info(f"📞 LLM 下载完成: {model_id}/{filename}")
            
            # 添加到 manifest
            if save_path.exists():
                file_size = save_path.stat().st_size
                add_model_to_manifest(
                    model_id,
                    filename,
                    save_path,
                    file_size,
                    parameters=request.parameters,
                    capabilities=request.capabilities
                )
            
            # 如果不是 mmproj 文件，检测并下载 mmproj
            if not is_mmproj:
                await _download_mmproj_background(
                    model_id,
                    use_mirror,
                    request.parameters,
                    request.capabilities
                )
        
        # 启动后台下载任务（使用 V2 管理器）
        result = await manager.start_download(
            model_type="llm",
            model_id=llm_task_id,
            hf_repo_id=model_id,
            save_dir=save_dir,
            filename=filename,
            use_mirror=use_mirror,
            parameters=request.parameters,
            capabilities=request.capabilities,
            on_complete=on_complete
        )
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "启动下载失败")
            )
        
        return {
            "status": "started",
            "message": "下载任务已启动，请通过进度接口查询状态",
            "task_id": llm_task_id,
            "model_id": model_id,
            "filename": filename,
            "progress_url": f"/huggingface/download/progress/{model_id}?filename={filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _download_mmproj_background(
    model_id: str,
    use_mirror: bool,
    parameters: Optional[str] = None,
    capabilities: Optional[List[str]] = None
):
    """
    后台检测并下载 mmproj 文件
    """
    try:
        # 获取模型文件列表
        files = fetch_model_files(model_id, use_mirror=use_mirror)
        
        # 查找 mmproj 文件
        mmproj_filename = find_mmproj_file(files)
        
        if not mmproj_filename:
            logger.info(f"📷 模型 {model_id} 没有 mmproj 文件")
            return
        
        # 检查是否已下载
        if is_mmproj_downloaded(model_id, mmproj_filename):
            logger.info(f"📷 mmproj 文件已存在: {mmproj_filename}")
            return
        
        logger.info(f"📷 后台下载 mmproj 文件: {mmproj_filename}")
        
        # 下载 mmproj 文件
        mmproj_save_path = get_model_storage_path(model_id, mmproj_filename)
        mmproj_task_id = get_llm_task_id(model_id, mmproj_filename)
        
        manager = get_hf_download_manager_v2()
        
        async def on_mmproj_complete(model_type: str, task_id: str):
            logger.info(f"📷 mmproj 下载完成: {mmproj_filename}")
            if mmproj_save_path.exists():
                file_size = mmproj_save_path.stat().st_size
                add_model_to_manifest(
                    model_id,
                    mmproj_filename,
                    mmproj_save_path,
                    file_size,
                    parameters=parameters,
                    capabilities=capabilities
                )
        
        await manager.start_download(
            model_type="llm_mmproj",
            model_id=mmproj_task_id,
            hf_repo_id=model_id,
            save_dir=mmproj_save_path.parent,
            filename=mmproj_filename,
            use_mirror=use_mirror,
            parameters=parameters,
            capabilities=capabilities,
            on_complete=on_mmproj_complete
        )
        
    except Exception as e:
        logger.error(f"后台下载 mmproj 文件失败: {e}", exc_info=True)


@router.get("/download/progress/{model_id:path}")
async def get_download_progress(model_id: str, filename: str = Query(...)):
    """
    获取下载进度（轮询模式）
    
    Args:
        model_id: 模型 ID (如 "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")
        filename: 文件名 (Query 参数)
    
    Returns:
        下载进度信息
    """
    try:
        llm_task_id = get_llm_task_id(model_id, filename)
        manager = get_hf_download_manager_v2()
        
        progress = manager.get_progress("llm", llm_task_id)
        
        # 添加额外信息
        progress["model_id"] = model_id
        progress["filename"] = filename
        progress["task_id"] = llm_task_id
        
        return progress
        
    except Exception as e:
        logger.error(f"获取下载进度失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/cancel")
async def cancel_download(request: CancelDownloadRequest):
    """
    取消下载（删除临时文件）
    
    取消后会删除所有临时文件
    
    Args:
        request: 取消请求
    """
    try:
        model_id = request.model_id
        filename = request.filename
        task_id = get_task_id(model_id, filename)
        llm_task_id = get_llm_task_id(model_id, filename)
        
        manager = get_hf_download_manager_v2()
        
        # 使用 V2 管理器取消下载
        result = await manager.request_cancel("llm", llm_task_id)
        
        logger.info(f"🗑️ 取消下载 [{task_id}]: {result}")
        
        return {
            "status": "success",
            "message": "已取消下载"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消下载失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download/pause")
async def pause_download(request: PauseDownloadRequest):
    """
    暂停下载（保留临时文件用于断点续传）
    
    暂停后可以通过 resume=True 的下载请求恢复。
    
    Args:
        request: 暂停请求
    """
    try:
        model_id = request.model_id
        filename = request.filename
        task_id = get_task_id(model_id, filename)
        llm_task_id = get_llm_task_id(model_id, filename)
        
        manager = get_hf_download_manager_v2()
        
        # 请求暂停
        result = await manager.request_pause("llm", llm_task_id)
        
        logger.info(f"⏸️ 已请求暂停下载 [{task_id}]: {result}")
        return {
            "status": "success",
            "message": "已请求暂停下载"
        }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"暂停下载失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/pending")
async def get_pending_downloads():
    """
    获取所有可恢复的下载任务
    
    Returns:
        可恢复的下载任务列表
    """
    try:
        manager = get_hf_download_manager_v2()
        
        # 获取所有待恢复任务，然后过滤 LLM 相关的
        all_tasks = manager.get_pending_downloads()
        
        # 过滤 LLM 相关任务
        pending_tasks = []
        for task in all_tasks:
            model_type = task.get("model_type", "")
            if model_type in ["llm", "llm_mmproj"]:
                hf_repo_id = task.get("hf_repo_id", "")
                
                pending_tasks.append({
                    "model_id": hf_repo_id,
                    "filename": task.get("filename", "") or task.get("target_filename", ""),
                    "task_id": task.get("model_id", ""),
                    "total_bytes": task.get("total_bytes", 0),
                    "downloaded_bytes": task.get("downloaded_bytes", 0),
                    "progress": task.get("progress", 0),
                    "status": task.get("status", ""),
                    "error_message": task.get("error_message")
                })
        
        logger.info(f"📋 发现 {len(pending_tasks)} 个可恢复的 LLM 下载任务")
        
        return {
            "status": "success",
            "count": len(pending_tasks),
            "tasks": pending_tasks
        }
        
    except Exception as e:
        logger.error(f"获取待恢复任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
async def list_sources():
    """
    获取可用的数据源列表
    
    将来可扩展添加更多数据源
    """
    return {
        "status": "success",
        "sources": [
            {
                "id": "lmstudio-community",
                "name": "LM Studio Community",
                "description": "由 LM Studio 社区维护的 GGUF 模型",
                "url": "https://huggingface.co/lmstudio-community"
            }
        ],
        "mirrors": [
            {
                "id": "hf-mirror",
                "name": "HF-Mirror",
                "description": "HuggingFace 国内镜像站",
                "url": "https://hf-mirror.com",
                "default": True
            }
        ]
    }
