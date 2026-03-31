"""
GitHub Release 下载管理器

支持功能:
- HTTP Range 断点续传
- ghproxy.com 镜像加速
- 进度跟踪和持久化
- 暂停/取消/恢复
- 文件完整性校验 (Content-Length)
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import threading
import time
from typing import Dict, Optional

import aiohttp

from app.config import Config
from app.services.network_service import NetworkService
from app.utils.logger import get_logger

logger = get_logger("github_download")


# ============================================================================
# 下载状态枚举 (与 hf_download_v2 保持一致)
# ============================================================================

class DownloadStatus(str, Enum):
    """下载状态"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# 下载元信息
# ============================================================================

@dataclass
class GitHubDownloadMeta:
    """
    GitHub 下载元信息 - 用于进度跟踪和断点续传
    
    保存到 .github_{task_id}_download_meta.json 文件
    """
    task_id: str                 # 任务标识
    original_url: str            # 原始下载 URL
    mirror_url: str              # 镜像 URL (如果启用)
    save_path: str               # 保存路径
    total_bytes: int             # 总字节数
    downloaded_bytes: int        # 已下载字节数
    status: str                  # 下载状态
    use_mirror: bool             # 是否使用镜像
    started_at: str              # 开始时间
    updated_at: str              # 更新时间
    speed_display: str = ""      # 格式化速度 "1.5 MB/s"
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GitHubDownloadMeta':
        return cls(
            task_id=data.get("task_id", ""),
            original_url=data.get("original_url", ""),
            mirror_url=data.get("mirror_url", ""),
            save_path=data.get("save_path", ""),
            total_bytes=data.get("total_bytes") or 0,
            downloaded_bytes=data.get("downloaded_bytes") or 0,
            status=data.get("status", DownloadStatus.PENDING.value),
            use_mirror=data.get("use_mirror", True),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            speed_display=data.get("speed_display", ""),
            error_message=data.get("error_message"),
        )
    
    def save(self, meta_path: Path):
        """保存到文件"""
        self.updated_at = datetime.now().isoformat()
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"保存 meta 文件失败: {e}")
    
    @classmethod
    def load(cls, meta_path: Path) -> Optional['GitHubDownloadMeta']:
        """从文件加载"""
        try:
            if meta_path.exists():
                with open(meta_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls.from_dict(data)
        except Exception as e:
            logger.warning(f"加载 meta 文件失败: {e}")
        return None


# ============================================================================
# 辅助函数
# ============================================================================

def format_speed(bytes_per_second: float) -> str:
    """格式化下载速度"""
    if bytes_per_second <= 0:
        return ""
    if bytes_per_second > 1024 * 1024:
        return f"{bytes_per_second / 1024 / 1024:.1f} MB/s"
    elif bytes_per_second > 1024:
        return f"{bytes_per_second / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_second:.0f} B/s"


def get_github_mirror_url(url: str, use_mirror: bool = True) -> str:
    """
    获取 GitHub 镜像 URL
    
    支持的 URL 格式:
    - https://github.com/owner/repo/releases/download/tag/file
    - https://raw.githubusercontent.com/owner/repo/branch/file
    """
    if not use_mirror:
        return url
    
    # ghproxy.com 镜像
    if "github.com" in url or "raw.githubusercontent.com" in url:
        return f"https://ghproxy.com/{url}"
    
    return url


# ============================================================================
# 取消信号管理器 (线程安全)
# ============================================================================

class CancelSignalManager:
    """线程安全的取消信号管理器"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._cancel_signals: Dict[str, bool] = {}
        self._pause_signals: Dict[str, bool] = {}
    
    def set_cancel(self, task_id: str):
        """设置取消信号"""
        with self._lock:
            self._cancel_signals[task_id] = True
    
    def set_pause(self, task_id: str):
        """设置暂停信号"""
        with self._lock:
            self._pause_signals[task_id] = True
    
    def clear(self, task_id: str):
        """清除信号"""
        with self._lock:
            self._cancel_signals.pop(task_id, None)
            self._pause_signals.pop(task_id, None)
    
    def is_cancelled(self, task_id: str) -> bool:
        """检查是否被取消"""
        with self._lock:
            return self._cancel_signals.get(task_id, False)
    
    def is_paused(self, task_id: str) -> bool:
        """检查是否被暂停"""
        with self._lock:
            return self._pause_signals.get(task_id, False)
    
    def should_stop(self, task_id: str) -> bool:
        """检查是否应该停止（取消或暂停）"""
        with self._lock:
            return self._cancel_signals.get(task_id, False) or self._pause_signals.get(task_id, False)


# 全局取消信号管理器
_cancel_signal_manager = CancelSignalManager()


# ============================================================================
# GitHub 下载管理器
# ============================================================================

class GitHubDownloadManager:
    """
    GitHub Release 下载管理器
    
    支持:
    - HTTP Range 断点续传
    - ghproxy.com 镜像加速
    - 进度持久化
    - 暂停/取消/恢复
    - 文件完整性校验
    """
    
    _instance = None
    _initialized = False
    
    # 下载配置
    CHUNK_SIZE = 64 * 1024  # 64KB chunks
    TIMEOUT = aiohttp.ClientTimeout(total=None, connect=30, sock_read=60)
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 活动下载任务
        self._active_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("GitHubDownloadManager 初始化完成")
    
    def _get_task_id(self, url: str) -> str:
        """从 URL 生成任务 ID"""
        # 提取文件名作为任务 ID 的一部分
        filename = url.split("/")[-1].replace(".", "_")
        return f"github_{filename}"
    
    def _get_meta_path(self, task_id: str) -> Path:
        """获取 meta 文件路径"""
        return Config.DATA_DIR / f".{task_id}_download_meta.json"
    
    async def start_download(
        self,
        url: str,
        save_path: Path,
        *,
        task_id: Optional[str] = None,
        use_mirror: Optional[bool] = None,
        resume: bool = True,
        url_candidates: Optional[list[str]] = None,
    ) -> dict:
        """
        启动下载任务
        
        Args:
            url: GitHub Release 下载 URL
            save_path: 保存路径
            task_id: 自定义任务 ID (可选)
            use_mirror: 是否使用镜像（兼容旧参数，None 时使用策略配置）
            resume: 是否恢复下载 (默认 True)
        
        Returns:
            状态字典
        """
        if task_id is None:
            task_id = self._get_task_id(url)
        
        meta_path = self._get_meta_path(task_id)
        
        logger.info(f"📥 启动 GitHub 下载: [{task_id}]")
        logger.info(f"   URL: {url}")
        logger.info(f"   保存路径: {save_path}")
        logger.info(f"   镜像偏好: {use_mirror}")
        
        # 检查是否已在下载
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if not task.done():
                logger.warning(f"任务已在进行中: {task_id}")
                return {"status": "already_downloading", "task_id": task_id}
        
        # 清除信号
        _cancel_signal_manager.clear(task_id)
        
        # 确保父目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 计算已下载字节数 (用于断点续传)
        downloaded_bytes = 0
        if resume and save_path.exists():
            downloaded_bytes = save_path.stat().st_size
            logger.info(f"   发现已下载: {downloaded_bytes} bytes，将尝试续传")
        
        resolved_candidates = url_candidates
        if not resolved_candidates:
            resolved_candidates = await NetworkService.resolve_github_url_candidates(
                url=url,
                explicit_use_mirror=use_mirror,
            )
        resolved_candidates = [candidate for candidate in (resolved_candidates or []) if candidate]
        if not resolved_candidates:
            mirror_url = get_github_mirror_url(url, True)
            resolved_candidates = [mirror_url, url] if mirror_url != url else [url]
        first_candidate = resolved_candidates[0]
        resolved_use_mirror = first_candidate != url
        
        # 创建或加载 meta
        if resume and meta_path.exists():
            meta = GitHubDownloadMeta.load(meta_path)
            if meta:
                meta.status = DownloadStatus.DOWNLOADING.value
                meta.downloaded_bytes = downloaded_bytes
                meta.mirror_url = first_candidate
                meta.use_mirror = resolved_use_mirror
                meta.save(meta_path)
        else:
            meta = GitHubDownloadMeta(
                task_id=task_id,
                original_url=url,
                mirror_url=first_candidate,
                save_path=str(save_path),
                total_bytes=0,
                downloaded_bytes=downloaded_bytes,
                status=DownloadStatus.DOWNLOADING.value,
                use_mirror=resolved_use_mirror,
                started_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            meta.save(meta_path)
        
        # 启动后台任务
        task = asyncio.create_task(
            self._download_in_background(
                task_id=task_id,
                url=url,
                urls_to_try=resolved_candidates,
                save_path=save_path,
                downloaded_bytes=downloaded_bytes,
            )
        )
        self._active_tasks[task_id] = task
        
        return {
            "status": "started",
            "task_id": task_id,
            "use_mirror": resolved_use_mirror,
            "resumed_from": downloaded_bytes,
        }
    
    async def _download_in_background(
        self,
        task_id: str,
        url: str,
        urls_to_try: list[str],
        save_path: Path,
        downloaded_bytes: int,
    ):
        """后台下载任务"""
        meta_path = self._get_meta_path(task_id)
        temp_path = save_path.with_suffix(save_path.suffix + ".downloading")
        
        # 如果有部分下载，复制到临时文件继续
        if downloaded_bytes > 0 and save_path.exists():
            import shutil
            shutil.copy2(save_path, temp_path)
        
        try:
            for attempt, download_url in enumerate(urls_to_try):
                try:
                    await self._do_download(
                        task_id=task_id,
                        url=download_url,
                        save_path=save_path,
                        temp_path=temp_path,
                        initial_bytes=downloaded_bytes,
                    )
                    await NetworkService.record_provider_success("github", download_url)
                    break  # 下载成功
                except Exception as e:
                    if attempt < len(urls_to_try) - 1:
                        logger.warning(f"下载源失败，尝试下一个 URL: {download_url} - {e}")
                        downloaded_bytes = 0  # 重置，从头开始
                        if temp_path.exists():
                            temp_path.unlink()
                    else:
                        raise
            
            # 检查是否被暂停或取消
            if _cancel_signal_manager.is_paused(task_id):
                meta = GitHubDownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.PAUSED.value
                    meta.save(meta_path)
                logger.info(f"⏸️ [{task_id}] 下载已暂停")
                return
            
            if _cancel_signal_manager.is_cancelled(task_id):
                meta = GitHubDownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.CANCELLED.value
                    meta.save(meta_path)
                # 清理临时文件
                if temp_path.exists():
                    temp_path.unlink()
                logger.info(f"⛔ [{task_id}] 下载被取消")
                return
            
            # 下载完成
            meta = GitHubDownloadMeta.load(meta_path)
            if meta:
                meta.status = DownloadStatus.COMPLETED.value
                meta.downloaded_bytes = meta.total_bytes
                meta.speed_display = ""
                meta.save(meta_path)
            
            logger.info(f"✅ [{task_id}] 下载完成: {save_path}")
        
        except asyncio.CancelledError:
            meta = GitHubDownloadMeta.load(meta_path)
            if meta and meta.status == DownloadStatus.DOWNLOADING.value:
                meta.status = DownloadStatus.CANCELLED.value
                meta.save(meta_path)
            logger.info(f"⛔ [{task_id}] 下载被取消 (asyncio)")
        
        except Exception as e:
            error_msg = str(e)
            if _cancel_signal_manager.should_stop(task_id):
                is_paused = _cancel_signal_manager.is_paused(task_id)
                if is_paused:
                    logger.info(f"⏸️ [{task_id}] 下载已暂停")
                else:
                    logger.info(f"⛔ [{task_id}] 下载被取消")
            else:
                logger.error(f"❌ [{task_id}] 下载失败: {e}", exc_info=True)
                meta = GitHubDownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.FAILED.value
                    meta.error_message = error_msg
                    meta.save(meta_path)
        
        finally:
            self._active_tasks.pop(task_id, None)
            _cancel_signal_manager.clear(task_id)
    
    async def _do_download(
        self,
        task_id: str,
        url: str,
        save_path: Path,
        temp_path: Path,
        initial_bytes: int,
    ):
        """执行实际下载"""
        meta_path = self._get_meta_path(task_id)
        
        headers = {}
        if initial_bytes > 0:
            headers["Range"] = f"bytes={initial_bytes}-"
            logger.info(f"[{task_id}] 使用 Range 请求从 {initial_bytes} 字节继续")
        
        async with aiohttp.ClientSession(timeout=self.TIMEOUT) as session:
            async with session.get(url, headers=headers) as response:
                # 检查响应状态
                if response.status == 416:
                    # Range Not Satisfiable - 文件已完整下载
                    if temp_path.exists():
                        temp_path.rename(save_path)
                    logger.info(f"[{task_id}] 文件已完整下载")
                    return
                
                if response.status not in (200, 206):
                    raise Exception(f"HTTP {response.status}: {response.reason}")
                
                # 获取总大小
                content_length = response.headers.get("Content-Length")
                if content_length:
                    if response.status == 206:
                        # 部分内容，需要加上已下载的部分
                        total_bytes = initial_bytes + int(content_length)
                    else:
                        total_bytes = int(content_length)
                else:
                    total_bytes = 0
                
                # 更新 meta
                meta = GitHubDownloadMeta.load(meta_path)
                if meta and total_bytes > 0:
                    meta.total_bytes = total_bytes
                    meta.save(meta_path)
                
                logger.info(f"[{task_id}] 开始下载: 总大小={total_bytes}, 已下载={initial_bytes}")
                
                # 打开文件写入
                mode = "ab" if initial_bytes > 0 and response.status == 206 else "wb"
                downloaded = initial_bytes if mode == "ab" else 0
                
                last_update_time = time.time()
                last_downloaded = downloaded
                last_log_time = 0.0
                
                with open(temp_path, mode) as f:
                    async for chunk in response.content.iter_chunked(self.CHUNK_SIZE):
                        # 检查停止信号
                        if _cancel_signal_manager.should_stop(task_id):
                            # 保存当前进度
                            meta = GitHubDownloadMeta.load(meta_path)
                            if meta:
                                meta.downloaded_bytes = downloaded
                                if _cancel_signal_manager.is_paused(task_id):
                                    meta.status = DownloadStatus.PAUSED.value
                                else:
                                    meta.status = DownloadStatus.CANCELLED.value
                                meta.save(meta_path)
                            
                            # 如果是暂停，保留临时文件
                            if _cancel_signal_manager.is_paused(task_id):
                                temp_path.rename(save_path)
                            return
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        now = time.time()
                        elapsed = now - last_update_time
                        
                        # 每 0.5 秒更新一次进度
                        if elapsed >= 0.5:
                            bytes_delta = downloaded - last_downloaded
                            speed = bytes_delta / elapsed if elapsed > 0 else 0
                            speed_str = format_speed(speed)
                            
                            # 更新 meta
                            meta = GitHubDownloadMeta.load(meta_path)
                            if meta:
                                meta.downloaded_bytes = downloaded
                                meta.speed_display = speed_str
                                meta.save(meta_path)
                            
                            # 日志（每 2 秒一次）
                            if now - last_log_time >= 2.0:
                                if total_bytes > 0:
                                    pct = downloaded / total_bytes * 100
                                    logger.info(f"[{task_id}] 下载进度: {pct:.1f}% ({downloaded}/{total_bytes}) {speed_str}")
                                else:
                                    logger.info(f"[{task_id}] 已下载: {downloaded} bytes {speed_str}")
                                last_log_time = now
                            
                            last_update_time = now
                            last_downloaded = downloaded
                
                # 下载完成，验证大小
                if total_bytes > 0 and downloaded != total_bytes:
                    raise Exception(f"文件大小不匹配: 期望 {total_bytes}, 实际 {downloaded}")
                
                # 重命名临时文件为最终文件
                if temp_path.exists():
                    if save_path.exists():
                        save_path.unlink()
                    temp_path.rename(save_path)
    
    def get_progress(self, task_id: str) -> dict:
        """获取下载进度"""
        meta_path = self._get_meta_path(task_id)
        
        meta = GitHubDownloadMeta.load(meta_path)
        if not meta:
            return {"status": "not_found"}
        
        total = meta.total_bytes or 0
        downloaded = meta.downloaded_bytes or 0
        progress = (downloaded / total * 100) if total > 0 else 0
        
        return {
            "status": meta.status,
            "progress": round(progress, 2),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "speed": meta.speed_display,
            "error_message": meta.error_message,
        }
    
    def get_progress_by_url(self, url: str) -> dict:
        """通过 URL 获取下载进度"""
        task_id = self._get_task_id(url)
        return self.get_progress(task_id)
    
    async def request_pause(self, task_id: str) -> dict:
        """请求暂停下载"""
        meta_path = self._get_meta_path(task_id)
        
        logger.info(f"⏸️ 请求暂停: {task_id}")
        
        # 设置暂停信号
        _cancel_signal_manager.set_pause(task_id)
        
        # 立即更新 meta 状态
        meta = GitHubDownloadMeta.load(meta_path)
        if meta:
            meta.status = DownloadStatus.PAUSED.value
            meta.save(meta_path)
        
        return {"status": "paused", "task_id": task_id}
    
    async def request_cancel(self, task_id: str) -> dict:
        """请求取消下载"""
        meta_path = self._get_meta_path(task_id)
        
        logger.info(f"⛔ 请求取消: {task_id}")
        
        # 设置取消信号
        _cancel_signal_manager.set_cancel(task_id)
        
        # 立即更新 meta 状态
        meta = GitHubDownloadMeta.load(meta_path)
        if meta:
            meta.status = DownloadStatus.CANCELLED.value
            meta.save(meta_path)
        
        # 清理已下载的文件
        if meta:
            save_path = Path(meta.save_path)
            if save_path.exists():
                try:
                    save_path.unlink()
                    logger.info(f"已删除部分下载文件: {save_path}")
                except Exception as e:
                    logger.warning(f"删除文件失败: {e}")
        
        return {"status": "cancelled", "task_id": task_id}
    
    def is_active(self, task_id: str) -> bool:
        """检查任务是否活跃"""
        task = self._active_tasks.get(task_id)
        return task is not None and not task.done()
    
    def is_active_by_url(self, url: str) -> bool:
        """通过 URL 检查任务是否活跃"""
        task_id = self._get_task_id(url)
        return self.is_active(task_id)


# ============================================================================
# 单例获取
# ============================================================================

_manager_instance: Optional[GitHubDownloadManager] = None


def get_github_download_manager() -> GitHubDownloadManager:
    """获取下载管理器实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = GitHubDownloadManager()
    return _manager_instance
