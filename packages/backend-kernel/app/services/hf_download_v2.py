"""
HuggingFace 模型下载管理器 V2

基于官方 huggingface_hub 的 tqdm_class 机制实现进度跟踪。

核心设计（参考官方 _snapshot_download.py 实现）：
1. 对于 snapshot_download：
   - 传入的 tqdm_class 用于创建 bytes_progress（字节级进度条，unit="B"）
   - 还用于 thread_map 的外层进度条（文件数量进度条）
   - _AggregatedTqdm 内部类会调用 bytes_progress.update(n) 更新字节进度

2. 对于 hf_hub_download：
   - 传入的 tqdm_class 直接用于字节级下载进度

通过 unit 参数区分进度条类型：
- unit="B" 且 unit_scale=True：字节级进度，需要追踪
- 其他：文件级进度，可以忽略
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.config import Config
from app.services.network_service import NetworkService
from app.utils.logger import get_logger

logger = get_logger("hf_download_v2")

REPO_DOWNLOAD_MARKER = "__repo__"

# ============================================================================
# 禁用 hf_xet（Rust 加速库）
# 原因：hf_xet 使用 Rust 实现，其进度回调机制与 Python tqdm_class 不兼容
# 禁用后强制使用 HTTP 下载，确保 tqdm_class.update() 被正确调用
# ============================================================================
os.environ["HF_HUB_DISABLE_XET"] = "1"
logger.info("已禁用 hf_xet，使用标准 HTTP 下载以确保进度追踪正常")


# ============================================================================
# 下载状态枚举
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
class DownloadMeta:
    """
    下载元信息 - 用于进度跟踪和断点续传
    
    保存到 .{model_type}_{model_id}_download_meta.json 文件
    """
    model_type: str              # "vibevoice", "whisper", "llm" 等
    model_id: str                # 模型标识
    hf_repo_id: str              # HuggingFace 仓库 ID
    save_dir: str                # 保存目录
    total_bytes: int             # 总字节数
    downloaded_bytes: int        # 已下载字节数
    status: str                  # 下载状态
    use_mirror: bool             # 是否使用镜像
    started_at: str              # 开始时间
    updated_at: str              # 更新时间
    speed_display: str = ""      # 格式化速度 "1.5 MB/s"
    error_message: Optional[str] = None
    # 单文件模式
    is_single_file: bool = False
    target_filename: str = ""
    # LLM 模型额外信息
    parameters: Optional[str] = None
    capabilities: Optional[List[str]] = None
    model_format: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DownloadMeta':
        # 确保数值类型不为 None
        total_bytes = data.get("total_bytes")
        downloaded_bytes = data.get("downloaded_bytes")
        
        return cls(
            model_type=data.get("model_type", ""),
            model_id=data.get("model_id", ""),
            hf_repo_id=data.get("hf_repo_id", ""),
            save_dir=data.get("save_dir", ""),
            total_bytes=total_bytes if total_bytes is not None else 0,
            downloaded_bytes=downloaded_bytes if downloaded_bytes is not None else 0,
            status=data.get("status", DownloadStatus.PENDING.value),
            use_mirror=data.get("use_mirror", True),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            speed_display=data.get("speed_display", ""),
            error_message=data.get("error_message"),
            is_single_file=data.get("is_single_file", False),
            target_filename=data.get("target_filename", ""),
            parameters=data.get("parameters"),
            capabilities=data.get("capabilities"),
            model_format=data.get("model_format")
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
    def load(cls, meta_path: Path) -> Optional['DownloadMeta']:
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
# 回调类型
# ============================================================================

OnCompleteCallback = Callable[[str, str], Awaitable[None]]  # (model_type, model_id)


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


def detect_model_format_from_filename(filename: str) -> Optional[str]:
    lower = filename.lower()
    if lower.endswith(".gguf"):
        return "gguf"
    if lower.endswith(".safetensors") or "mlx" in lower:
        return "mlx"
    return None


def get_hf_endpoint(use_mirror: bool) -> str:
    """获取 HuggingFace endpoint"""
    if use_mirror:
        return "https://hf-mirror.com"
    return "https://huggingface.co"


def is_hf_mirror_endpoint(endpoint: str) -> bool:
    return "hf-mirror.com" in (endpoint or "")


# ============================================================================
# 自定义异常：用于中断下载
# ============================================================================

class DownloadInterruptedError(Exception):
    """下载被中断（暂停或取消）"""
    pass


# ============================================================================
# 全局取消信号管理（线程安全）
# ============================================================================

class CancelSignalManager:
    """
    线程安全的取消信号管理器
    
    用于在下载线程中检测取消/暂停信号。
    huggingface_hub 的下载在 asyncio.to_thread 中执行，无法直接被 asyncio.cancel 中断，
    所以我们在 tqdm.update() 回调中检查这个信号，如果检测到取消就抛出异常。
    """
    
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
# 全局进度追踪状态（线程安全）
# ============================================================================

class ProgressState:
    """线程安全的进度状态"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._states: Dict[str, Dict[str, Any]] = {}
    
    def init(self, task_id: str, meta_path: Path):
        """初始化任务状态"""
        with self._lock:
            self._states[task_id] = {
                "meta_path": meta_path,
                "total_bytes": 0,
                "downloaded_bytes": 0,
                "total_files": 0,
                "completed_files": 0,
                "current_file": "",
                "last_update": time.time(),
                "last_downloaded": 0,
            }
    
    def update_bytes(self, task_id: str, downloaded: int, total: int, speed_str: str = ""):
        """更新字节进度"""
        with self._lock:
            state = self._states.get(task_id)
            if not state:
                return
            
            state["downloaded_bytes"] = downloaded
            effective_total = total
            
            # 更新 meta 文件
            try:
                meta_path = state["meta_path"]
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.downloaded_bytes = downloaded
                    if meta.is_single_file:
                        if total > 0:
                            meta.total_bytes = total
                    else:
                        if meta.total_bytes > 0:
                            effective_total = meta.total_bytes
                        elif total > 0:
                            meta.total_bytes = total
                    if speed_str:
                        meta.speed_display = speed_str
                    meta.save(meta_path)
            except Exception as e:
                logger.debug(f"更新 meta 失败: {e}")
            
            if effective_total > 0:
                state["total_bytes"] = effective_total
    
    def update_files(self, task_id: str, completed: int, total: int, current_file: str = ""):
        """更新文件进度（用于 repo 下载）"""
        with self._lock:
            state = self._states.get(task_id)
            if not state:
                return
            
            state["completed_files"] = completed
            if total > 0:
                state["total_files"] = total
            if current_file:
                state["current_file"] = current_file
    
    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取状态"""
        with self._lock:
            return self._states.get(task_id, {}).copy()
    
    def remove(self, task_id: str):
        """移除任务状态"""
        with self._lock:
            self._states.pop(task_id, None)


# 全局进度状态实例
_progress_state = ProgressState()


# ============================================================================
# 自定义进度跟踪器（模块级别定义）
# ============================================================================

def create_progress_tracker_class(task_id: str) -> type:
    """
    创建自定义进度跟踪器类
    
    这个类会被传递给 hf_hub_download/snapshot_download 的 tqdm_class 参数。
    
    在 snapshot_download 中，tqdm_class 会被用于两种进度条：
    1. bytes_progress - 字节级进度（unit="B", unit_scale=True）
    2. thread_map 的文件级进度（没有 unit="B"，用于追踪文件数量）
    
    重要功能：
    1. 检测取消/暂停信号，通过抛出异常来中断下载线程
    2. 自己维护计数器，不依赖 tqdm 的 self.n（当 disable=True 时 self.n 不更新）
    3. 区分字节级和文件级进度，分别追踪
    """
    from tqdm.auto import tqdm as base_tqdm
    
    class ProgressTracker(base_tqdm):
        """自定义进度跟踪器"""
        
        def __init__(self, *args, **kwargs):
            # 保存原始参数用于判断
            self._unit = kwargs.get('unit', 'it')
            self._unit_scale = kwargs.get('unit_scale', False)
            self._desc = kwargs.get('desc', '')
            
            # 判断进度条类型
            # 字节级进度：unit="B" 且 unit_scale=True
            self._is_bytes_progress = (self._unit == 'B' and self._unit_scale)
            # 文件级进度：来自 thread_map，通常 desc 包含 "Fetching"
            self._is_files_progress = not self._is_bytes_progress and 'Fetching' in str(self._desc)
            
            # 获取 initial 值
            initial = kwargs.get('initial', 0)
            
            # 我们自己维护的计数器（关键修复）
            self._downloaded_bytes = initial
            self._completed_files = 0
            
            # 保存 total
            self._total_bytes = kwargs.get('total', 0) or 0
            self._total_files = kwargs.get('total', 0) or 0
            
            # 过滤掉 tqdm 不支持的参数（huggingface_hub 新版本会传递 'name' 参数）
            unsupported_keys = {'name'}
            filtered_kwargs = {k: v for k, v in kwargs.items() if k not in unsupported_keys}
            
            super().__init__(*args, **filtered_kwargs)
            
            # 用于计算速度
            self._last_update_time = time.time()
            self._last_downloaded = initial
            
            # 用于控制日志频率
            self._last_log_time = 0
            
            if self._is_bytes_progress:
                logger.debug(f"[{task_id}] 创建字节级进度条: total={self._total_bytes}, initial={initial}")
            elif self._is_files_progress:
                logger.debug(f"[{task_id}] 创建文件级进度条: total={self._total_files}, desc={self._desc}")
        
        def update(self, n: int = 1) -> Optional[bool]:
            # ============ 关键：检查取消/暂停信号 ============
            # 这是唯一能够中断 huggingface_hub 下载线程的地方
            if _cancel_signal_manager.should_stop(task_id):
                is_paused = _cancel_signal_manager.is_paused(task_id)
                action = "暂停" if is_paused else "取消"
                logger.info(f"🛑 [{task_id}] 检测到{action}信号，中断下载")
                raise DownloadInterruptedError(f"下载被{action}")
            
            # ============ 更新进度 ============
            if self._is_bytes_progress and n > 0:
                # 字节级进度
                self._downloaded_bytes += n
                # 同步更新 _total_bytes（可能被外部通过 self.total 更新）
                if self.total and self.total > self._total_bytes:
                    self._total_bytes = self.total
            elif self._is_files_progress and n > 0:
                # 文件级进度
                self._completed_files += int(n)
                if self.total and self.total > 0:
                    self._total_files = int(self.total)
            
            # 调用父类的 update
            result = super().update(n)
            
            now = time.time()
            elapsed = now - self._last_update_time
            
            # ============ 更新字节级进度 ============
            if self._is_bytes_progress and elapsed >= 0.5:
                # 计算速度
                bytes_delta = self._downloaded_bytes - self._last_downloaded
                speed = bytes_delta / elapsed if elapsed > 0 else 0
                speed_str = format_speed(speed)
                
                # 获取最新的 total
                current_total = self.total if self.total and self.total > 0 else self._total_bytes
                
                # 更新全局状态
                _progress_state.update_bytes(
                    task_id,
                    downloaded=self._downloaded_bytes,
                    total=current_total,
                    speed_str=speed_str
                )
                
                # 日志（限制频率，每2秒一次）
                if now - self._last_log_time >= 2.0:
                    if current_total > 0:
                        pct = self._downloaded_bytes / current_total * 100
                        logger.info(f"[{task_id}] 下载进度: {pct:.1f}% ({self._downloaded_bytes}/{current_total}) {speed_str}")
                    else:
                        logger.info(f"[{task_id}] 已下载: {self._downloaded_bytes} bytes {speed_str}")
                    self._last_log_time = now
                
                self._last_update_time = now
                self._last_downloaded = self._downloaded_bytes
            
            # ============ 更新文件级进度 ============
            elif self._is_files_progress and n > 0:
                # 更新文件进度
                _progress_state.update_files(
                    task_id,
                    completed=self._completed_files,
                    total=self._total_files,
                    current_file=""
                )
                logger.debug(f"[{task_id}] 文件进度: {self._completed_files}/{self._total_files}")
            
            return result
        
        def close(self):
            if self._is_bytes_progress:
                # 获取最新的 total
                current_total = self.total if self.total and self.total > 0 else self._total_bytes
                # 最终更新
                _progress_state.update_bytes(
                    task_id,
                    downloaded=self._downloaded_bytes,
                    total=current_total,
                    speed_str=""
                )
                logger.debug(f"[{task_id}] 字节进度条关闭: downloaded={self._downloaded_bytes}, total={current_total}")
            elif self._is_files_progress:
                _progress_state.update_files(
                    task_id,
                    completed=self._completed_files,
                    total=self._total_files
                )
                logger.debug(f"[{task_id}] 文件进度条关闭: {self._completed_files}/{self._total_files}")
            super().close()
    
    return ProgressTracker


# ============================================================================
# HuggingFace 下载管理器 V2
# ============================================================================

class HFDownloadManagerV2:
    """
    HuggingFace 下载管理器 V2
    
    使用官方 API + 自定义 tqdm_class 进度跟踪器。
    支持暂停/取消功能（通过在 tqdm.update() 中检查信号并抛出异常）。
    """
    
    _instance = None
    _initialized = False
    
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
        
        logger.info("HFDownloadManagerV2 初始化完成")
    
    def _get_task_id(self, model_type: str, model_id: str) -> str:
        """生成任务 ID"""
        safe_id = model_id.replace("/", "_").replace("\\", "_")
        return f"{model_type}_{safe_id}"
    
    def _get_meta_path(self, task_id: str) -> Path:
        """获取 meta 文件路径"""
        return Config.DATA_DIR / f".{task_id}_download_meta.json"
    
    async def start_download(
        self,
        model_type: str,
        model_id: str,
        hf_repo_id: str,
        save_dir: Path,
        *,
        use_mirror: Optional[bool] = None,
        resume: bool = False,
        filename: Optional[str] = None,  # 如果指定，则下载单个文件
        on_complete: Optional[OnCompleteCallback] = None,
        parameters: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        endpoint_candidates: Optional[List[str]] = None,
    ) -> dict:
        """
        启动下载任务
        
        Args:
            model_type: 模型类型 ("vibevoice", "whisper", "llm" 等)
            model_id: 模型标识
            hf_repo_id: HuggingFace 仓库 ID
            save_dir: 保存目录
            use_mirror: 是否使用镜像（兼容旧参数，None 时使用策略配置）
            resume: 是否恢复下载
            filename: 如果指定，只下载单个文件
            on_complete: 下载完成回调
            parameters: LLM 模型参数
            capabilities: LLM 模型能力
        """
        normalized_filename = None if filename == REPO_DOWNLOAD_MARKER else filename
        task_id = self._get_task_id(model_type, model_id)
        meta_path = self._get_meta_path(task_id)
        is_single_file = normalized_filename is not None
        
        if is_single_file:
            logger.info(f"📥 启动单文件下载: [{task_id}] -> {normalized_filename}")
        else:
            logger.info(f"📥 启动仓库下载: [{task_id}] -> {hf_repo_id}")
        
        # 检查是否已在下载
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            if not task.done():
                logger.warning(f"任务已在进行中: {task_id}")
                return {"status": "already_downloading", "task_id": task_id}
        
        # 清除信号
        _cancel_signal_manager.clear(task_id)
        
        # 创建或加载 meta
        save_dir.mkdir(parents=True, exist_ok=True)
        
        resolved_candidates = endpoint_candidates
        if not resolved_candidates:
            resolved_candidates = await NetworkService.resolve_hf_endpoint_candidates(use_mirror)
        resolved_candidates = [c for c in (resolved_candidates or []) if c]
        if not resolved_candidates:
            resolved_candidates = ["https://huggingface.co", "https://hf-mirror.com"]
        resolved_use_mirror = is_hf_mirror_endpoint(resolved_candidates[0])

        if resume and meta_path.exists():
            meta = DownloadMeta.load(meta_path)
            if meta:
                meta.status = DownloadStatus.DOWNLOADING.value
                meta.use_mirror = resolved_use_mirror
                if normalized_filename and not meta.model_format:
                    meta.model_format = detect_model_format_from_filename(normalized_filename)
                meta.save(meta_path)
        else:
            meta = DownloadMeta(
                model_type=model_type,
                model_id=model_id,
                hf_repo_id=hf_repo_id,
                save_dir=str(save_dir),
                total_bytes=0,
                downloaded_bytes=0,
                status=DownloadStatus.DOWNLOADING.value,
                use_mirror=resolved_use_mirror,
                started_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                is_single_file=is_single_file,
                target_filename=filename or "",
                parameters=parameters,
                capabilities=capabilities,
                model_format=detect_model_format_from_filename(normalized_filename) if normalized_filename else None,
            )
            meta.save(meta_path)
        
        # 初始化进度状态
        _progress_state.init(task_id, meta_path)
        
        # 启动后台任务
        task = asyncio.create_task(
            self._download_in_background(
                task_id=task_id,
                hf_repo_id=hf_repo_id,
                save_dir=save_dir,
                endpoint_candidates=resolved_candidates,
                filename=normalized_filename,
                on_complete=on_complete,
            )
        )
        self._active_tasks[task_id] = task
        
        return {
            "status": "started",
            "task_id": task_id,
            "model_type": model_type,
            "model_id": model_id,
        }
    
    async def _download_in_background(
        self,
        task_id: str,
        hf_repo_id: str,
        save_dir: Path,
        endpoint_candidates: List[str],
        filename: Optional[str],
        on_complete: Optional[OnCompleteCallback],
    ):
        """后台下载任务"""
        meta_path = self._get_meta_path(task_id)
        
        try:
            # 创建自定义进度跟踪器类
            ProgressTrackerClass = create_progress_tracker_class(task_id)
            
            last_error: Optional[Exception] = None
            for endpoint in endpoint_candidates:
                try:
                    if filename:
                        await self._download_single_file(
                            task_id=task_id,
                            hf_repo_id=hf_repo_id,
                            filename=filename,
                            save_dir=save_dir,
                            endpoint=endpoint,
                            ProgressTrackerClass=ProgressTrackerClass,
                        )
                    else:
                        await self._download_repository(
                            task_id=task_id,
                            hf_repo_id=hf_repo_id,
                            save_dir=save_dir,
                            endpoint=endpoint,
                            ProgressTrackerClass=ProgressTrackerClass,
                        )
                    await NetworkService.record_provider_success("huggingface", endpoint)
                    break
                except Exception as e:
                    last_error = e
                    logger.warning(f"[{task_id}] endpoint 失败，尝试下一个: {endpoint} - {e}")
            else:
                raise RuntimeError(f"all_hf_endpoints_failed: {last_error}")
            
            # 检查是否被暂停（正常完成后检查）
            if _cancel_signal_manager.is_paused(task_id):
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.PAUSED.value
                    meta.save(meta_path)
                logger.info(f"⏸️ [{task_id}] 下载已暂停")
                return
            
            # 检查是否被取消（正常完成后检查）
            if _cancel_signal_manager.is_cancelled(task_id):
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.CANCELLED.value
                    meta.save(meta_path)
                logger.info(f"⛔ [{task_id}] 下载被取消")
                return
            
            meta = DownloadMeta.load(meta_path)
            if meta:
                state = _progress_state.get(task_id)
                total_files = int(state.get("total_files", 0)) if state else 0

                can_confirm_completion = bool(meta.total_bytes > 0 or total_files > 0)
                if not can_confirm_completion:
                    meta.status = DownloadStatus.FAILED.value
                    meta.error_message = "无法获取仓库元信息，未能确认下载是否完整（可能被镜像限流）"
                    meta.speed_display = ""
                    meta.save(meta_path)
                    logger.warning(f"❌ [{task_id}] 下载结束但无法确认完整性")
                    return

                meta.status = DownloadStatus.COMPLETED.value
                if meta.total_bytes > 0:
                    meta.downloaded_bytes = meta.total_bytes
                meta.speed_display = ""
                meta.error_message = None
                meta.save(meta_path)

            logger.info(f"✅ [{task_id}] 下载完成")

            if on_complete:
                parts = task_id.split("_", 1)
                if len(parts) == 2:
                    await on_complete(parts[0], parts[1])
        
        except DownloadInterruptedError:
            # 下载被中断（暂停或取消）
            # 状态已经在 request_pause/request_cancel 中更新，这里只记录日志
            is_paused = _cancel_signal_manager.is_paused(task_id)
            if is_paused:
                logger.info(f"⏸️ [{task_id}] 下载已暂停（通过中断）")
            else:
                logger.info(f"⛔ [{task_id}] 下载被取消（通过中断）")
        
        except asyncio.CancelledError:
            # asyncio 任务被取消（备用机制）
            meta = DownloadMeta.load(meta_path)
            if meta and meta.status == DownloadStatus.DOWNLOADING.value:
                meta.status = DownloadStatus.CANCELLED.value
                meta.save(meta_path)
            logger.info(f"⛔ [{task_id}] 下载被取消（asyncio）")
        
        except Exception as e:
            # 其他异常
            error_msg = str(e)
            # 检查是否是因为取消/暂停导致的异常
            if _cancel_signal_manager.should_stop(task_id):
                is_paused = _cancel_signal_manager.is_paused(task_id)
                if is_paused:
                    logger.info(f"⏸️ [{task_id}] 下载已暂停")
                else:
                    logger.info(f"⛔ [{task_id}] 下载被取消")
            else:
                logger.error(f"❌ [{task_id}] 下载失败: {e}", exc_info=True)
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.status = DownloadStatus.FAILED.value
                    meta.error_message = error_msg
                    meta.save(meta_path)
        
        finally:
            # 清理
            self._active_tasks.pop(task_id, None)
            _cancel_signal_manager.clear(task_id)
            _progress_state.remove(task_id)
    
    async def _download_single_file(
        self,
        task_id: str,
        hf_repo_id: str,
        filename: str,
        save_dir: Path,
        endpoint: str,
        ProgressTrackerClass: type,
    ):
        """下载单个文件"""
        from huggingface_hub import HfApi, hf_hub_download
        
        logger.info(f"⬇️ 开始下载文件: {hf_repo_id}/{filename}")
        logger.info(f"📁 保存路径: {save_dir}")
        logger.info(f"🌐 Endpoint: {endpoint}")
        
        meta_path = self._get_meta_path(task_id)
        
        # 获取文件大小
        try:
            api = HfApi(endpoint=endpoint)
            model_info = await asyncio.to_thread(
                api.model_info,
                repo_id=hf_repo_id,
                files_metadata=True,
            )
            
            file_size = 0
            if model_info.siblings:
                for sibling in model_info.siblings:
                    if sibling.rfilename == filename:
                        file_size = sibling.size or 0
                        break
            
            if file_size > 0:
                logger.info(f"📊 文件大小: {file_size} bytes")
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.total_bytes = file_size
                    meta.save(meta_path)
        except Exception as e:
            logger.warning(f"获取文件大小失败: {e}")
        
        # 执行下载
        def do_download():
            return hf_hub_download(
                repo_id=hf_repo_id,
                filename=filename,
                local_dir=str(save_dir),
                endpoint=endpoint,
                tqdm_class=ProgressTrackerClass,
            )
        
        result = await asyncio.to_thread(do_download)
        logger.info(f"✅ 文件已下载: {result}")
        return result
    
    async def _download_repository(
        self,
        task_id: str,
        hf_repo_id: str,
        save_dir: Path,
        endpoint: str,
        ProgressTrackerClass: type,
    ):
        """下载整个仓库"""
        from huggingface_hub import HfApi, snapshot_download
        
        logger.info(f"⬇️ 开始下载仓库: {hf_repo_id}")
        logger.info(f"📁 保存路径: {save_dir}")
        logger.info(f"🌐 Endpoint: {endpoint}")
        
        meta_path = self._get_meta_path(task_id)
        
        # 获取仓库总大小
        try:
            api = HfApi(endpoint=endpoint)
            model_info = await asyncio.to_thread(
                api.model_info,
                repo_id=hf_repo_id,
                files_metadata=True,
            )
            
            total_size = 0
            file_count = 0
            if model_info.siblings:
                for sibling in model_info.siblings:
                    if sibling.size:
                        total_size += sibling.size
                    file_count += 1
            
            if total_size > 0:
                logger.info(f"📊 仓库总大小: {total_size} bytes ({file_count} 个文件)")
                meta = DownloadMeta.load(meta_path)
                if meta:
                    meta.total_bytes = total_size
                    meta.save(meta_path)
        except Exception as e:
            logger.warning(f"获取仓库大小失败: {e}")
        
        # 执行下载
        def do_download():
            return snapshot_download(
                repo_id=hf_repo_id,
                local_dir=str(save_dir),
                endpoint=endpoint,
                tqdm_class=ProgressTrackerClass,
            )
        
        result = await asyncio.to_thread(do_download)
        logger.info(f"✅ 仓库已下载: {result}")
        return result
    
    def get_progress(self, model_type: str, model_id: str) -> dict:
        """获取下载进度"""
        task_id = self._get_task_id(model_type, model_id)
        meta_path = self._get_meta_path(task_id)
        
        meta = DownloadMeta.load(meta_path)
        if not meta:
            return {"status": "not_found"}
        
        total = meta.total_bytes or 0
        downloaded = meta.downloaded_bytes or 0
        progress = (downloaded / total * 100) if total > 0 else 0
        
        # 获取实时进度状态（包含文件进度）
        state = _progress_state.get(task_id)
        
        result = {
            "status": meta.status,
            "progress": round(progress, 2),
            "downloaded_bytes": downloaded,
            "total_bytes": total,
            "speed": meta.speed_display,
            "error_message": meta.error_message,
            "is_single_file": meta.is_single_file,
            "filename": meta.target_filename,
        }
        
        # 添加文件进度信息（用于 repo 下载）
        if state:
            completed_files = state.get("completed_files", 0)
            total_files = state.get("total_files", 0)
            current_file = state.get("current_file", "")
            
            if total_files > 0:
                result["completed_files"] = completed_files
                result["total_files"] = total_files
            if current_file:
                result["current_file"] = current_file

            if total <= 0 and total_files > 0:
                try:
                    result["progress"] = round((float(completed_files) / float(total_files)) * 100.0, 2)
                except Exception:
                    pass
        
        return result
    
    async def request_pause(self, model_type: str, model_id: str) -> dict:
        """
        请求暂停下载
        
        工作原理：
        1. 设置暂停信号到 CancelSignalManager
        2. 下载线程在 tqdm.update() 中检测到信号后抛出 DownloadInterruptedError
        3. 异常被捕获，下载停止，状态更新为 PAUSED
        """
        task_id = self._get_task_id(model_type, model_id)
        meta_path = self._get_meta_path(task_id)
        
        logger.info(f"⏸️ 请求暂停: {task_id}")
        
        # 设置暂停信号（线程安全）
        _cancel_signal_manager.set_pause(task_id)
        
        # 立即更新 meta 状态
        meta = DownloadMeta.load(meta_path)
        if meta:
            meta.status = DownloadStatus.PAUSED.value
            meta.save(meta_path)
        
        return {"status": "paused", "task_id": task_id}
    
    async def request_cancel(self, model_type: str, model_id: str) -> dict:
        """
        请求取消下载
        
        工作原理：
        1. 设置取消信号到 CancelSignalManager
        2. 下载线程在 tqdm.update() 中检测到信号后抛出 DownloadInterruptedError
        3. 异常被捕获，下载停止，状态更新为 CANCELLED
        """
        task_id = self._get_task_id(model_type, model_id)
        meta_path = self._get_meta_path(task_id)
        
        logger.info(f"⛔ 请求取消: {task_id}")
        
        # 设置取消信号（线程安全）
        _cancel_signal_manager.set_cancel(task_id)
        
        # 立即更新 meta 状态
        meta = DownloadMeta.load(meta_path)
        if meta:
            meta.status = DownloadStatus.CANCELLED.value
            meta.save(meta_path)
        
        return {"status": "cancelled", "task_id": task_id}
    
    def is_active(self, model_type: str, model_id: str) -> bool:
        """检查任务是否活跃"""
        task_id = self._get_task_id(model_type, model_id)
        task = self._active_tasks.get(task_id)
        return task is not None and not task.done()
    
    def get_pending_downloads(self) -> List[dict]:
        """获取所有未完成下载任务（下载中/暂停/失败）"""
        pending = []
        
        for meta_file in Config.DATA_DIR.glob(".*_download_meta.json"):
            try:
                meta = DownloadMeta.load(meta_file)
                if meta and meta.status in [
                    DownloadStatus.PENDING.value,
                    DownloadStatus.PAUSED.value,
                    DownloadStatus.DOWNLOADING.value,
                    DownloadStatus.FAILED.value,
                ]:
                    progress = self.get_progress(meta.model_type, meta.model_id)
                    pending.append({
                        "model_type": meta.model_type,
                        "model_id": meta.model_id,
                        "hf_repo_id": meta.hf_repo_id,
                        "status": progress.get("status", meta.status),
                        "progress": progress.get("progress", 0),
                        "downloaded_bytes": progress.get("downloaded_bytes", meta.downloaded_bytes or 0),
                        "total_bytes": progress.get("total_bytes", meta.total_bytes or 0),
                        "speed": progress.get("speed", meta.speed_display),
                        "error_message": progress.get("error_message", meta.error_message),
                        "started_at": meta.started_at,
                        "updated_at": meta.updated_at,
                        "is_single_file": meta.is_single_file,
                        "filename": meta.target_filename,
                    })
            except Exception as e:
                logger.warning(f"读取 meta 文件失败 {meta_file}: {e}")
        
        return pending


# ============================================================================
# 单例获取
# ============================================================================

_manager_instance: Optional[HFDownloadManagerV2] = None


def get_hf_download_manager_v2() -> HFDownloadManagerV2:
    """获取下载管理器实例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = HFDownloadManagerV2()
    return _manager_instance
