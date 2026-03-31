"""
ZenMind - 模型管理服务
管理模型下载任务（HuggingFace Hub）、进度跟踪、本地模型扫描

文件命名规范：
- 下载中: filename.gguf.downloading
- 下载完成: filename.gguf
- manifest.json 记录所有已下载模型的元信息

目录结构：
models/
├── manifest.json
└── {author}/
    └── {model_name}_{hash}/
        └── {filename}.gguf
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import Config
from app.utils.logger import setup_logger

logger = setup_logger("zenmind.model_manager", log_file=Config.LOGS_DIR / "models.log")


@dataclass
class DownloadTask:
    """下载任务"""
    model_id: str
    model_name: str
    status: str  # pending, downloading, completed, failed, cancelled
    progress: float  # 0-100
    downloaded_bytes: int
    total_bytes: int
    speed: str  # 下载速度
    eta: str  # 预计剩余时间
    started_at: str
    updated_at: str
    error_message: Optional[str] = None
    cancel_requested: bool = False


class ModelManager:
    """
    模型管理器
    
    职责：
    1. 模型注册表管理
    2. 从 HuggingFace 下载模型
    3. 本地模型扫描
    4. 模型删除
    """
    
    _instance: Optional['ModelManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.download_tasks: Dict[str, DownloadTask] = {}
        self.registry: Dict = {}
        self._load_registry()
        self._manifest_path = Config.MODELS_DIR / "manifest.json"
        self._local_manifest: Dict = {}
        self._load_local_manifest()
        
        # 启动时检查未完成的下载（不再自动清理，保留可恢复的任务）
        self._check_incomplete_downloads()
        
        logger.info("模型管理器已初始化 (HuggingFace 模式)")
    
    def _check_incomplete_downloads(self):
        """
        检查未完成的下载文件
        
        在应用启动时调用，统计可恢复的下载任务。
        
        规则：
        - 如果 .downloading 文件有对应的 .download_meta 文件，保留（可恢复）
        - 如果 .downloading 文件没有 .download_meta 文件，清理（孤立文件）
        """
        try:
            resumable_count = 0
            cleaned_count = 0
            
            for downloading_file in Config.MODELS_DIR.glob("**/*.downloading"):
                # 检查是否有对应的 .download_meta 文件
                meta_file = Path(str(downloading_file).replace(".downloading", ".download_meta"))
                
                if meta_file.exists():
                    # 有元信息文件，保留用于断点续传
                    resumable_count += 1
                    file_size = downloading_file.stat().st_size / (1024 * 1024)  # MB
                    logger.info(f"📂 发现可恢复的下载: {downloading_file.name} ({file_size:.1f} MB)")
                else:
                    # 没有元信息文件，清理孤立的下载文件
                    try:
                        downloading_file.unlink()
                        cleaned_count += 1
                        logger.info(f"🗑️ 已清理孤立的下载文件: {downloading_file}")
                    except Exception as e:
                        logger.warning(f"清理临时文件失败: {downloading_file}, 错误: {e}")
            
            if resumable_count > 0:
                logger.info(f"📋 发现 {resumable_count} 个可恢复的下载任务")
            if cleaned_count > 0:
                logger.info(f"✅ 共清理 {cleaned_count} 个孤立的下载文件")
                
        except Exception as e:
            logger.warning(f"检查未完成下载时出错: {e}")
    
    def _load_registry(self):
        """加载模型注册表"""
        import sys
        
        # 在打包环境中，数据文件位于 sys._MEIPASS 目录
        meipass = getattr(sys, "_MEIPASS", None)
        if getattr(sys, "frozen", False) and meipass:
            registry_path = Path(meipass) / "app" / "config" / "models_registry.json"
        else:
            registry_path = Config.BACKEND_ROOT / "app" / "config" / "models_registry.json"
        
        logger.info(f"加载模型注册表: {registry_path}")
        
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                self.registry = json.load(f)
            logger.info(f"✅ 已加载 {len(self.registry.get('models', []))} 个模型")
        except Exception as e:
            logger.error(f"❌ 加载模型注册表失败: {e}", exc_info=True)
            self.registry = {"models": [], "categories": [], "metadata": {}}
    
    def _load_local_manifest(self):
        """加载本地模型清单"""
        if self._manifest_path.exists():
            try:
                with open(self._manifest_path, 'r', encoding='utf-8') as f:
                    self._local_manifest = json.load(f)
            except Exception as e:
                logger.warning(f"加载本地清单失败: {e}")
                self._local_manifest = {"models": {}}
        else:
            self._local_manifest = {"models": {}}
        return self._local_manifest
    
    def _save_local_manifest(self):
        """保存本地模型清单"""
        try:
            with open(self._manifest_path, 'w', encoding='utf-8') as f:
                json.dump(self._local_manifest, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存本地清单失败: {e}")
    
    def get_registry(self) -> Dict:
        """获取模型注册表"""
        return self.registry
    
    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """获取模型信息"""
        for model in self.registry.get("models", []):
            if model["id"] == model_id:
                return model
        return None
    
    def get_model_path(self, model_id: str) -> Optional[Path]:
        """获取模型文件路径"""
        if not model_id:
            return None
            
        # 1. 直接作为相对路径查找 (处理 get_installed_models 返回的 ID)
        # ID 通常是 "author/repo_hash/filename.gguf"
        try:
            direct_path = Config.MODELS_DIR / model_id
            if direct_path.exists():
                if direct_path.is_file() or direct_path.is_dir():
                    return direct_path
        except Exception:
            pass

        # 2. 从本地清单（manifest.json）中查找
        # 遍历 manifest 查找匹配的 model_id 或 relative_path
        for info in self._local_manifest.get("models", {}).values():
            # 匹配 Short ID (例如: lmstudio-community/Qwen3-VL-2B-Instruct-GGUF)
            if info.get("model_id") == model_id:
                relative_path = info.get("relative_path")
                if relative_path:
                    model_path = Config.MODELS_DIR / relative_path
                    if model_path.exists():
                        return model_path
            
            # 匹配 Relative Path (防止 ID 格式差异)
            if info.get("relative_path") == model_id:
                relative_path = info.get("relative_path")
                if relative_path:
                    model_path = Config.MODELS_DIR / relative_path
                    if model_path.exists():
                        return model_path

        # 3. 回退到注册表查找（兼容旧逻辑或手动放置的文件）
        model_info = self.get_model_info(model_id)
        if model_info:
            local_filename = model_info.get("local_filename")
            if local_filename:
                model_path = Config.MODELS_DIR / local_filename
                if model_path.exists():
                    return model_path
        
        return None
    
    def filter_models(
        self, 
        family: Optional[str] = None,
        provider: Optional[str] = None,
        tags: Optional[List[str]] = None,
        max_size: Optional[int] = None
    ) -> List[Dict]:
        """筛选模型"""
        models = self.registry.get("models", [])
        
        if family:
            models = [m for m in models if m.get("family") == family]
        
        if provider:
            models = [m for m in models if m.get("provider") == provider]
        
        if tags:
            models = [m for m in models if any(tag in m.get("tags", []) for tag in tags)]
        
        if max_size:
            models = [m for m in models if m.get("size", 0) <= max_size]
        
        return models
    
    def get_installed_models(self) -> List[Dict]:
        """
        获取已安装的模型列表
        
        扫描逻辑：
        1. 递归扫描 models 目录下所有模型文件（.gguf / .safetensors）
        2. 排除 .downloading 后缀的临时文件
        3. 从 manifest.json 获取元信息
        4. 计算相对路径用于唯一标识
        
        目录结构示例：
        models/
        ├── manifest.json
        └── lmstudio-community/
            └── gemma-3-1B-it-qat-GGUF_7e446ddb/
                └── gemma-3-1B-it-QAT-Q4_0.gguf
        """
        models = []
        manifest = self._load_local_manifest()
        manifest_models = manifest.get("models", {})
        
        for model_file in Config.MODELS_DIR.glob("**/*"):
            if not model_file.is_file():
                continue
            name_lower = model_file.name.lower()
            if not (name_lower.endswith(".gguf") or name_lower.endswith(".safetensors")):
                continue
            if name_lower.endswith(".downloading"):
                continue
            if model_file.name == "manifest.json":
                continue
            try:
                stat = model_file.stat()
            except Exception as e:
                logger.warning(f"无法获取文件状态: {model_file}, 错误: {e}")
                continue
            try:
                relative_path = model_file.relative_to(Config.MODELS_DIR)
            except ValueError:
                relative_path = Path(model_file.name)
            path_parts = str(relative_path).split(os.sep)
            author = path_parts[0] if len(path_parts) > 1 else None
            manifest_info = None
            for key, info in manifest_models.items():
                if info.get("path") == str(model_file) or info.get("filename") == model_file.name:
                    manifest_info = info
                    break
            model_id = str(relative_path).replace(os.sep, "/")
            registry_info = None
            for m in self.registry.get("models", []):
                if m.get("local_filename") == model_file.name:
                    registry_info = m
                    break
            models.append({
                "id": model_id,
                "filename": model_file.name,
                "path": str(model_file),
                "relative_path": str(relative_path),
                "size": stat.st_size,
                "size_display": self._format_size(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "author": manifest_info.get("author") if manifest_info else author,
                "huggingface_id": manifest_info.get("model_id") if manifest_info else None,
                "downloaded_at": manifest_info.get("downloaded_at") if manifest_info else None,
                "name": registry_info.get("name") if registry_info else model_file.stem,
                "family": registry_info.get("family") if registry_info else None,
                "provider": registry_info.get("provider") if registry_info else None,
                "parameters": (manifest_info.get("parameters") if manifest_info else None) or (registry_info.get("parameters") if registry_info else None),
                "capabilities": (manifest_info.get("capabilities") if manifest_info else None) or (registry_info.get("capabilities") if registry_info else []),
                "context_length": (manifest_info.get("context_length") if manifest_info else None) or (registry_info.get("context_length") if registry_info else None),
                "format": manifest_info.get("format") if manifest_info else (
                    "gguf" if name_lower.endswith(".gguf") else "mlx"
                ),
            })
        
        # 按修改时间倒序排列（最新的在前）
        models.sort(key=lambda x: str(x.get("modified_at", "")), reverse=True)
        
        return models
    
    def is_model_installed(self, model_id: str) -> bool:
        """检查模型是否已安装"""
        return self.get_model_path(model_id) is not None
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def create_download_task(self, model_id: str) -> DownloadTask:
        """创建下载任务"""
        model_info = self.get_model_info(model_id)
        if not model_info:
            raise ValueError(f"未知的模型: {model_id}")
        
        now = datetime.now().isoformat()
        task = DownloadTask(
            model_id=model_id,
            model_name=model_info["name"],
            status="pending",
            progress=0.0,
            downloaded_bytes=0,
            total_bytes=model_info.get("size", 0),
            speed="0 MB/s",
            eta="计算中...",
            started_at=now,
            updated_at=now
        )
        
        self.download_tasks[model_id] = task
        logger.info(f"创建下载任务: {model_id}")
        return task
    
    async def download_model(self, model_id: str) -> AsyncIterator[Dict]:
        """
        下载模型（从 HuggingFace）
        
        Args:
            model_id: 模型 ID
        
        Yields:
            进度更新字典
        """
        model_info = self.get_model_info(model_id)
        if not model_info:
            yield {"status": "error", "error": f"未知的模型: {model_id}"}
            return
        
        # 检查必要字段
        hf_repo_id = model_info.get("hf_repo_id")
        hf_filename = model_info.get("hf_filename")
        local_filename = model_info.get("local_filename")
        
        if not all([hf_repo_id, hf_filename, local_filename]):
            yield {"status": "error", "error": "模型配置不完整，缺少 HuggingFace 信息"}
            return
        local_filename_str = str(local_filename)
        
        # 创建下载任务
        task = self.create_download_task(model_id)
        task.status = "downloading"
        
        yield {
            "status": "starting",
            "model_id": model_id,
            "model_name": model_info["name"],
            "hf_repo_id": hf_repo_id,
            "hf_filename": hf_filename,
        }
        
        try:
            import time

            from huggingface_hub import hf_hub_download
            from huggingface_hub.utils.tqdm import tqdm as hf_tqdm
            
            # 确保目录存在
            Config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
            
            # 设置 HF 缓存目录
            os.environ["HF_HOME"] = str(Config.HF_CACHE_DIR)
            
            # 进度队列
            progress_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
            download_complete = asyncio.Event()
            download_error = None
            final_path = None
            
            def sync_download():
                nonlocal download_error, final_path
                
                try:
                    # 自定义 tqdm 类以捕获进度
                    class ProgressCallback(hf_tqdm):
                        def __init__(self, *args, **kwargs):
                            super().__init__(*args, **kwargs)
                            self._last_update = time.time()
                            self._last_n = 0
                        
                        def update(self, n=1):
                            super().update(n)
                            now = time.time()
                            
                            # 每 0.5 秒更新一次
                            if now - self._last_update >= 0.5:
                                speed = (self.n - self._last_n) / (now - self._last_update)
                                speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed > 0 else "计算中..."
                                logger.info(f"下载速度: {speed_str}")
                                
                                eta = ""
                                if speed > 0 and self.total:
                                    remaining = self.total - self.n
                                    eta_seconds = remaining / speed
                                    if eta_seconds < 60:
                                        eta = f"{int(eta_seconds)}s"
                                    elif eta_seconds < 3600:
                                        eta = f"{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s"
                                    else:
                                        eta = f"{int(eta_seconds / 3600)}h {int((eta_seconds % 3600) / 60)}m"
                                
                                progress_data = {
                                    "status": "downloading",
                                    "progress": (self.n / self.total * 100) if self.total else 0,
                                    "downloaded_bytes": self.n,
                                    "total_bytes": self.total,
                                    "speed": speed_str,
                                    "eta": eta,
                                }
                                
                                # 使用 call_soon_threadsafe 安全地放入队列
                                try:
                                    loop = asyncio.get_running_loop()
                                    loop.call_soon_threadsafe(
                                        progress_queue.put_nowait,
                                        progress_data
                                    )
                                except RuntimeError:
                                    pass
                                
                                self._last_update = now
                                self._last_n = self.n
                    
                    # 执行下载
                    downloaded_path = hf_hub_download(
                        repo_id=hf_repo_id,
                        filename=hf_filename,
                        local_dir=Config.MODELS_DIR,
                        local_dir_use_symlinks=False,
                        tqdm_class=ProgressCallback,
                    )
                    
                    # 如果下载的文件名与期望的不同，重命名
                    downloaded = Path(downloaded_path)
                    target = Config.MODELS_DIR / local_filename_str
                    
                    if downloaded != target:
                        if downloaded.exists():
                            shutil.move(str(downloaded), str(target))
                            final_path = target
                        else:
                            final_path = downloaded
                    else:
                        final_path = downloaded
                    
                except Exception as e:
                    download_error = str(e)
                finally:
                    download_complete.set()
            
            # 在线程中执行下载
            download_task = asyncio.create_task(asyncio.to_thread(sync_download))
            
            # 发送进度更新
            while not download_complete.is_set():
                try:
                    # 等待进度更新或完成
                    done, pending = await asyncio.wait(
                        [
                            asyncio.create_task(progress_queue.get()),
                            asyncio.create_task(download_complete.wait()),
                        ],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=1.0
                    )
                    
                    for task_done in done:
                        try:
                            result = task_done.result()
                            if isinstance(result, dict):
                                # 检查是否请求取消
                                if self.is_cancel_requested(model_id):
                                    yield {"status": "cancelled", "model_id": model_id}
                                    return
                                
                                # 更新任务状态
                                self.update_download_progress(
                                    model_id,
                                    progress=result.get("progress"),
                                    downloaded_bytes=result.get("downloaded_bytes"),
                                    total_bytes=result.get("total_bytes"),
                                    speed=result.get("speed"),
                                    eta=result.get("eta"),
                                )
                                
                                yield result
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            pass
                    
                    # 取消未完成的任务
                    for p in pending:
                        p.cancel()
                        
                except asyncio.TimeoutError:
                    continue
            
            # 等待下载任务完成
            await download_task
            
            if download_error:
                task.status = "failed"
                task.error_message = download_error
                yield {"status": "error", "error": download_error}
                return
            
            # 下载成功
            task.status = "completed"
            task.progress = 100.0
            
            # 更新本地清单
            self._local_manifest["models"][model_id] = {
                "filename": local_filename,
                "downloaded_at": datetime.now().isoformat(),
                "hf_repo_id": hf_repo_id,
                "hf_filename": hf_filename,
                "parameters": model_info.get("parameters"),
                "capabilities": model_info.get("capabilities"),
            }
            self._save_local_manifest()
            
            yield {
                "status": "completed",
                "model_id": model_id,
                "path": str(final_path) if final_path else None,
            }
            
        except Exception as e:
            logger.error(f"下载模型失败: {e}", exc_info=True)
            task.status = "failed"
            task.error_message = str(e)
            yield {"status": "error", "error": str(e)}
    
    async def delete_model(self, model_id: str) -> bool:
        """
        删除模型
        
        支持两种 model_id 格式：
        1. 相对路径: lmstudio-community/gemma-3-1B-it-qat-GGUF_7e446ddb/gemma-3-1B-it-QAT-Q4_0.gguf
        2. HuggingFace 格式: lmstudio-community/gemma-3-1B-it-qat-GGUF/gemma-3-1B-it-QAT-Q4_0.gguf
        
        Args:
            model_id: 模型 ID（相对路径或 HuggingFace 格式）
        
        Returns:
            是否删除成功
        """
        logger.info(f"🗑️ 尝试删除模型: {model_id}")
        
        model_path = None
        
        # 方法1: model_id 是相对路径，直接构造绝对路径
        potential_path = Config.MODELS_DIR / model_id
        if potential_path.exists():
            model_path = potential_path
        
        # 方法2: 在已安装模型中查找
        if not model_path:
            installed_models = self.get_installed_models()
            for model in installed_models:
                # 匹配 id 或 filename
                if model.get("id") == model_id or model.get("filename") == model_id:
                    model_path = Path(model["path"])
                    break
        
        # 方法3: 从注册表获取
        if not model_path:
            model_info = self.get_model_info(model_id)
            if model_info:
                local_filename = model_info.get("local_filename")
                if local_filename:
                    # 递归搜索
                    for gguf_file in Config.MODELS_DIR.glob(f"**/{local_filename}"):
                        model_path = gguf_file
                        break
        
        if not model_path or not model_path.exists():
            logger.warning(f"模型文件不存在: {model_id}")
            return False
        
        try:
            # 记录模型路径（用于从 manifest 中删除）
            model_filename = model_path.name
            
            # 删除模型文件
            model_path.unlink()
            logger.info(f"✅ 已删除模型文件: {model_path}")
            
            # 尝试删除空的父目录（清理目录结构）
            parent_dir = model_path.parent
            try:
                # 只删除空目录，最多向上两级
                for _ in range(2):
                    if parent_dir == Config.MODELS_DIR:
                        break
                    if parent_dir.exists() and not any(parent_dir.iterdir()):
                        parent_dir.rmdir()
                        logger.info(f"🗑️ 已删除空目录: {parent_dir}")
                        parent_dir = parent_dir.parent
                    else:
                        break
            except Exception as e:
                logger.debug(f"清理空目录时出错（可忽略）: {e}")
            
            # 更新本地清单 - 移除匹配的条目
            manifest_updated = False
            for key in list(self._local_manifest.get("models", {}).keys()):
                info = self._local_manifest["models"][key]
                if info.get("filename") == model_filename or info.get("path") == str(model_path):
                    del self._local_manifest["models"][key]
                    manifest_updated = True
                    logger.info(f"✅ 已从 manifest 移除: {key}")
                    break
            
            if manifest_updated:
                self._save_local_manifest()
            
            return True
        except Exception as e:
            logger.error(f"❌ 删除模型失败: {e}", exc_info=True)
            return False
    
    def update_download_progress(
        self,
        model_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        speed: Optional[str] = None,
        eta: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """更新下载进度"""
        task = self.download_tasks.get(model_id)
        if not task:
            return
        
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        if downloaded_bytes is not None:
            task.downloaded_bytes = downloaded_bytes
        if total_bytes is not None:
            task.total_bytes = total_bytes
        if speed:
            task.speed = speed
        if eta:
            task.eta = eta
        if error_message:
            task.error_message = error_message
        
        task.updated_at = datetime.now().isoformat()
    
    def get_download_task(self, model_id: str) -> Optional[DownloadTask]:
        """获取下载任务"""
        return self.download_tasks.get(model_id)
    
    def get_all_download_tasks(self) -> List[DownloadTask]:
        """获取所有下载任务"""
        return list(self.download_tasks.values())
    
    def request_cancel(self, model_id: str) -> bool:
        """请求取消下载"""
        task = self.download_tasks.get(model_id)
        if not task:
            return False
        
        if task.status in ["completed", "failed", "cancelled"]:
            return False
        
        task.cancel_requested = True
        logger.info(f"请求取消下载: {model_id}")
        return True
    
    def is_cancel_requested(self, model_id: str) -> bool:
        """检查是否请求取消"""
        task = self.download_tasks.get(model_id)
        return task.cancel_requested if task else False
    
    def remove_task(self, model_id: str):
        """移除任务"""
        if model_id in self.download_tasks:
            del self.download_tasks[model_id]
            logger.info(f"移除任务: {model_id}")
    
    def task_to_dict(self, task: DownloadTask) -> Dict:
        """转换任务为字典"""
        return asdict(task)


# 全局单例
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """获取模型管理器单例"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager



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


def find_mmproj_for_model(model_path: Path) -> Optional[Path]:
    """
    查找模型对应的 mmproj 文件
    
    在模型文件所在的目录中查找 mmproj 文件。
    视觉模型（如 Qwen-VL, Gemma-3）需要 mmproj 文件才能处理图像。
    
    Args:
        model_path: 模型文件路径
    
    Returns:
        mmproj 文件路径，如果没有则返回 None
    """
    if not model_path or not model_path.exists():
        return None
    
    # 获取模型所在目录
    model_dir = model_path.parent
    
    # 在同目录下查找 mmproj 文件
    for file in model_dir.glob("*.gguf"):
        if is_mmproj_file(file.name):
            logger.info(f"📷 找到 mmproj 文件: {file}")
            return file
    
    return None


def has_mmproj(model_path: Path) -> bool:
    """
    检查模型是否有对应的 mmproj 文件
    
    Args:
        model_path: 模型文件路径
    
    Returns:
        是否存在 mmproj 文件
    """
    return find_mmproj_for_model(model_path) is not None
