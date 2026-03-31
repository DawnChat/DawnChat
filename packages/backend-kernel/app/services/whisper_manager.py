"""
Whisper ASR 管理器

负责 Faster-Whisper 模型的下载、加载和推理，支持：
- 模型下载（通过通用 HF 下载器）
- 断点续传/暂停/恢复
- 模型懒加载
- 语音转文字（带 VAD 支持）
- 多种输出格式
- 转录进度上报

设计原则：
- 复用通用 HuggingFaceDownloadManager
- 单例模式管理模型实例
- 灵活的参数配置
- 长任务进度上报
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.config import Config
from app.services.hf_download_v2 import HFDownloadManagerV2, get_hf_download_manager_v2
from app.utils.logger import get_logger

logger = get_logger("whisper")


# ============================================================================
# Whisper 模型配置
# ============================================================================

class WhisperModelSize(str, Enum):
    """Whisper 模型规格"""
    TINY = "tiny"           # ~74MB, 最快
    BASE = "base"           # ~142MB
    SMALL = "small"         # ~466MB, 推荐
    MEDIUM = "medium"       # ~1.5GB
    LARGE_V3 = "large-v3"   # ~3GB, 最准


@dataclass
class WhisperModelInfo:
    """Whisper 模型信息"""
    size: WhisperModelSize
    hf_repo_id: str
    description: str
    languages: int
    size_mb: int
    

# CTranslate2 格式的模型仓库（faster-whisper 使用）
WHISPER_MODELS: Dict[WhisperModelSize, WhisperModelInfo] = {
    WhisperModelSize.TINY: WhisperModelInfo(
        size=WhisperModelSize.TINY,
        hf_repo_id="Systran/faster-whisper-tiny",
        description="最小模型，适合快速转录",
        languages=99,
        size_mb=74,
    ),
    WhisperModelSize.BASE: WhisperModelInfo(
        size=WhisperModelSize.BASE,
        hf_repo_id="Systran/faster-whisper-base",
        description="基础模型，平衡速度与质量",
        languages=99,
        size_mb=142,
    ),
    WhisperModelSize.SMALL: WhisperModelInfo(
        size=WhisperModelSize.SMALL,
        hf_repo_id="Systran/faster-whisper-small",
        description="推荐模型，质量好速度快",
        languages=99,
        size_mb=466,
    ),
    WhisperModelSize.MEDIUM: WhisperModelInfo(
        size=WhisperModelSize.MEDIUM,
        hf_repo_id="Systran/faster-whisper-medium",
        description="中等模型，质量更好",
        languages=99,
        size_mb=1500,
    ),
    WhisperModelSize.LARGE_V3: WhisperModelInfo(
        size=WhisperModelSize.LARGE_V3,
        hf_repo_id="Systran/faster-whisper-large-v3",
        description="最大模型，最高质量",
        languages=99,
        size_mb=3000,
    ),
}


# 默认 VAD 参数
DEFAULT_VAD_PARAMETERS = {
    "min_speech_duration_ms": 250,
    "min_silence_duration_ms": 2000,
    "speech_pad_ms": 400,
    "threshold": 0.5,
}


# 模型类型标识
MODEL_TYPE = "whisper"


# ============================================================================
# Whisper 管理器（单例）
# ============================================================================

class WhisperManager:
    """
    Whisper ASR 管理器（单例）
    
    职责：
    1. 模型下载管理（委托给通用 HF 下载器）
    2. 模型加载和卸载
    3. 语音转文字推理
    4. 多种输出格式支持
    """
    
    _instance: Optional['WhisperManager'] = None
    
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
        
        # 模型实例（懒加载）
        self._model = None
        self._current_model_size: Optional[WhisperModelSize] = None
        self._model_lock = asyncio.Lock()
        
        logger.info("Whisper 管理器已初始化")
    
    # ========== 模型信息查询 ==========
    
    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有可用的 Whisper 模型"""
        models = []
        for size, info in WHISPER_MODELS.items():
            model_dir = Config.WHISPER_MODELS_DIR / size.value
            is_installed = self._check_model_installed(model_dir)
            
            models.append({
                "size": size.value,
                "hf_repo_id": info.hf_repo_id,
                "description": info.description,
                "languages": info.languages,
                "size_mb": info.size_mb,
                "installed": is_installed,
                "path": str(model_dir) if is_installed else None,
            })
        
        return models
    
    def _check_model_installed(self, model_dir: Path) -> bool:
        """检查模型是否已安装"""
        if not model_dir.exists():
            return False
        
        # 检查必要文件（CTranslate2 格式）
        required_files = ["model.bin", "config.json"]
        for f in required_files:
            if not (model_dir / f).exists():
                return False
        
        return True
    
    def get_installed_models(self) -> List[str]:
        """获取已安装的模型列表"""
        installed = []
        for size in WhisperModelSize:
            model_dir = Config.WHISPER_MODELS_DIR / size.value
            if self._check_model_installed(model_dir):
                installed.append(size.value)
        return installed
    
    def get_default_model(self) -> Optional[str]:
        """获取默认使用的模型（返回已安装的最大模型）"""
        # 按优先级排序（从大到小）
        priority = [
            WhisperModelSize.LARGE_V3,
            WhisperModelSize.MEDIUM,
            WhisperModelSize.SMALL,
            WhisperModelSize.BASE,
            WhisperModelSize.TINY,
        ]
        
        for size in priority:
            model_dir = Config.WHISPER_MODELS_DIR / size.value
            if self._check_model_installed(model_dir):
                return size.value
        
        return None
    
    # ========== 下载相关（委托给通用下载器）==========
    
    async def download_model(
        self,
        model_size: str,
        use_mirror: Optional[bool] = None,
        resume: bool = False
    ) -> dict:
        """
        下载 Whisper 模型（使用 snapshot_download 下载整个仓库）
        
        Args:
            model_size: 模型规格 (tiny/base/small/medium/large-v3)
            use_mirror: 是否使用镜像
            resume: 是否为恢复下载
        
        Returns:
            下载启动状态
        """
        try:
            size_enum = WhisperModelSize(model_size)
        except ValueError:
            return {
                "status": "error",
                "message": f"不支持的模型规格: {model_size}"
            }
        
        model_info = WHISPER_MODELS[size_enum]
        save_dir = Config.WHISPER_MODELS_DIR / model_size
        
        logger.info(f"📥 启动 Whisper {model_size} 下载任务")
        
        return await self._hf_manager.start_download(
            model_type=MODEL_TYPE,
            model_id=model_size,
            hf_repo_id=model_info.hf_repo_id,
            save_dir=save_dir,
            use_mirror=use_mirror,
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
        # 过滤 Whisper 相关任务
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
    
    # ========== 模型加载 ==========
    
    async def load_model(
        self,
        model_size: str,
        device: str = "auto",
        compute_type: str = "auto",
    ) -> bool:
        """
        加载 Whisper 模型
        
        Args:
            model_size: 模型规格
            device: 设备 (auto/cpu/cuda)
            compute_type: 计算类型 (auto/int8/float16/float32)
        
        Returns:
            是否加载成功
        """
        try:
            size_enum = WhisperModelSize(model_size)
        except ValueError:
            logger.error(f"不支持的模型规格: {model_size}")
            return False
        
        model_dir = Config.WHISPER_MODELS_DIR / model_size
        
        if not self._check_model_installed(model_dir):
            logger.error(f"模型未安装: {model_size}")
            return False
        
        async with self._model_lock:
            # 如果已加载相同模型，直接返回
            if self._model is not None and self._current_model_size == size_enum:
                logger.info(f"模型 {model_size} 已加载")
                return True
            
            # 卸载当前模型
            if self._model is not None:
                current_size = self._current_model_size
                size_label = current_size.value if current_size else "unknown"
                logger.info(f"卸载当前模型: {size_label}")
                self._model = None
                self._current_model_size = None
            
            try:
                logger.info(f"🔄 加载 Whisper 模型: {model_size}")
                
                # 在后台线程中加载模型
                from faster_whisper import WhisperModel
                
                self._model = await asyncio.to_thread(
                    WhisperModel,
                    str(model_dir),
                    device=device,
                    compute_type=compute_type,
                )
                
                self._current_model_size = size_enum
                logger.info(f"✅ Whisper 模型加载成功: {model_size}")
                return True
                
            except Exception as e:
                logger.error(f"❌ 加载模型失败: {e}")
                self._model = None
                self._current_model_size = None
                return False
    
    async def unload_model(self):
        """卸载当前模型"""
        async with self._model_lock:
            if self._model is not None:
                current_size = self._current_model_size
                size_label = current_size.value if current_size else "unknown"
                logger.info(f"卸载 Whisper 模型: {size_label}")
                self._model = None
                self._current_model_size = None
    
    def get_loaded_model(self) -> Optional[str]:
        """获取当前加载的模型"""
        if self._current_model_size:
            return self._current_model_size.value
        return None
    
    # ========== 语音转文字 ==========
    
    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        model_size: Optional[str] = None,
        vad_filter: bool = True,
        vad_parameters: Optional[Dict[str, Any]] = None,
        word_timestamps: bool = False,
        output_format: str = "segments",
        initial_prompt: Optional[str] = None,
        hotwords: Optional[str] = None,
        prefix: Optional[str] = None,
        chunk_length: Optional[int] = None,
        condition_on_previous_text: Optional[bool] = None,
        temperature: Optional[float] = None,
        beam_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        语音转文字
        
        Args:
            audio_path: 音频文件路径
            language: 语言代码 (None 自动检测, zh/en/ja 等)
            model_size: 使用的模型规格（None 使用当前加载的或默认模型）
            vad_filter: 是否启用 VAD 过滤
            vad_parameters: VAD 参数
            word_timestamps: 是否生成单词级时间戳
            output_format: 输出格式 (text/segments/srt/vtt)
            initial_prompt: 提示词（用于引导识别）
            hotwords: 热词/提示短语（用于弱引导识别）
            prefix: 作为每个窗口开头的前缀文本
            chunk_length: 分段长度（秒），会覆盖特征提取器默认值
            condition_on_previous_text: 是否基于前文条件
            temperature: 采样温度
            beam_size: Beam search 大小
        
        Returns:
            {
                "text": "完整文本",
                "segments": [...],  # output_format="segments" 时
                "language": "zh",
                "language_probability": 0.99,
                "duration": 120.5,
            }
        """
        audio_file = Path(audio_path)
        if not audio_file.exists():
            return {
                "error": True,
                "message": f"音频文件不存在: {audio_path}"
            }
        
        # 确定使用的模型
        target_model_size = model_size
        if target_model_size is None:
            if self._current_model_size:
                target_model_size = self._current_model_size.value
            else:
                target_model_size = self.get_default_model()
        
        if target_model_size is None:
            return {
                "error": True,
                "message": "没有可用的 Whisper 模型，请先下载"
            }
        
        # 加载模型（如果需要）
        if self._model is None or (model_size and self._current_model_size and self._current_model_size.value != model_size):
            success = await self.load_model(target_model_size)
            if not success:
                return {
                    "error": True,
                    "message": f"无法加载模型: {target_model_size}"
                }
        
        # 准备 VAD 参数
        effective_vad_params = None
        if vad_filter:
            effective_vad_params = {**DEFAULT_VAD_PARAMETERS}
            if vad_parameters:
                effective_vad_params.update(vad_parameters)
        
        effective_condition = True if condition_on_previous_text is None else bool(condition_on_previous_text)
        effective_temperature = 0.0 if temperature is None else float(temperature)
        effective_beam_size = 5 if beam_size is None else int(beam_size)

        try:
            logger.info(f"🎤 开始转录: {audio_file.name}")
            
            # 获取当前事件循环，用于在后台线程中安全地调用异步进度上报
            loop = asyncio.get_running_loop()
            
            # 创建线程安全的进度回调
            from app.services.task_manager import report_progress
            
            def progress_callback(progress: float, message: str):
                """线程安全的进度回调"""
                try:
                    asyncio.run_coroutine_threadsafe(
                        report_progress(progress, message),
                        loop
                    )
                    # 不阻塞等待结果，只是提交任务
                except Exception as e:
                    logger.debug(f"进度上报失败（可忽略）: {e}")
            
            # 整个转录过程在后台线程中执行，避免阻塞事件循环
            # 注意：faster-whisper 的 transcribe() 返回生成器，
            # 实际解码在迭代时进行，所以 list(segments) 也要在后台线程
            result = await asyncio.to_thread(
                self._transcribe_sync,
                str(audio_file),
                language,
                vad_filter,
                effective_vad_params,
                word_timestamps,
                initial_prompt,
                hotwords,
                prefix,
                chunk_length,
                effective_condition,
                effective_temperature,
                effective_beam_size,
                output_format,
                target_model_size,
                progress_callback,  # 传入进度回调
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 转录失败: {e}")
            return {
                "error": True,
                "message": str(e)
            }
    
    def _transcribe_sync(
        self,
        audio_path: str,
        language: Optional[str],
        vad_filter: bool,
        vad_parameters: Optional[Dict[str, Any]],
        word_timestamps: bool,
        initial_prompt: Optional[str],
        hotwords: Optional[str],
        prefix: Optional[str],
        chunk_length: Optional[int],
        condition_on_previous_text: bool,
        temperature: float,
        beam_size: int,
        output_format: str,
        model_size: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        同步执行转录（在后台线程中调用）
        
        将整个转录过程放在后台线程中，包括：
        1. 调用 model.transcribe()
        2. 迭代收集 segments（这是实际解码发生的地方）
        3. 构建返回结果
        4. 在迭代过程中上报进度
        
        这样可以避免阻塞主事件循环，保持心跳等异步任务正常运行。
        
        Args:
            progress_callback: 进度回调函数，签名为 (progress: float, message: str) -> None
        """
        # 上报初始进度
        if progress_callback:
            progress_callback(0.05, "正在加载音频...")
        
        # 执行转录
        model = self._model
        if model is None:
            raise RuntimeError("模型未加载，无法转录")
        segments, info = model.transcribe(
            audio_path,
            language=language,
            vad_filter=vad_filter,
            vad_parameters=vad_parameters,
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
            hotwords=hotwords,
            prefix=prefix,
            chunk_length=chunk_length,
            condition_on_previous_text=condition_on_previous_text,
            temperature=temperature,
            beam_size=beam_size,
        )
        
        # 获取总时长用于计算进度
        total_duration = info.duration if info.duration > 0 else 1.0
        
        if progress_callback:
            progress_callback(0.1, f"开始转录（音频时长: {total_duration:.1f}s）...")
        
        # 收集所有 segments，同时上报进度
        # 这里是实际解码发生的地方
        segment_list = []
        last_progress_time = 0.0
        segment_count = 0
        
        for seg in segments:
            segment_list.append(seg)
            segment_count += 1
            
            # 根据当前 segment 的 end 时间计算进度
            # 预留 10% 给初始化，10% 给后处理，所以实际转录占 80%
            current_progress = 0.1 + (seg.end / total_duration) * 0.8
            current_progress = min(current_progress, 0.9)  # 最多到 90%
            
            # 每处理 5 秒的音频内容或每 10 个 segment 上报一次进度（避免过于频繁）
            if progress_callback and (seg.end - last_progress_time >= 5.0 or segment_count % 10 == 0):
                progress_callback(
                    current_progress,
                    f"正在转录... 已处理 {seg.end:.1f}s / {total_duration:.1f}s"
                )
                last_progress_time = seg.end
        
        # 上报后处理进度
        if progress_callback:
            progress_callback(0.92, "转录完成，正在整理结果...")
        
        # 构建结果
        full_text = " ".join([seg.text.strip() for seg in segment_list])
        
        result = {
            "error": False,
            "text": full_text,
            "language": info.language,
            "language_probability": info.language_probability,
            "duration": info.duration,
            "model_size": model_size,
        }
        
        # 根据输出格式处理
        if output_format == "text":
            pass  # 只返回 text
        elif output_format == "segments":
            result["segments"] = [
                {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                    "words": [
                        {
                            "word": w.word,
                            "start": w.start,
                            "end": w.end,
                            "probability": w.probability,
                        }
                        for w in (seg.words or [])
                    ] if word_timestamps else None,
                    "avg_logprob": seg.avg_logprob,
                    "no_speech_prob": seg.no_speech_prob,
                }
                for seg in segment_list
            ]
        elif output_format == "srt":
            result["srt"] = self._format_srt(segment_list)
        elif output_format == "vtt":
            result["vtt"] = self._format_vtt(segment_list)
        
        # 上报完成进度
        if progress_callback:
            progress_callback(0.98, f"转录完成: {len(segment_list)} 个片段")
        
        logger.info(f"✅ 转录完成: {len(segment_list)} 个片段, 时长 {info.duration:.1f}s")
        return result
    
    def _format_srt(self, segments) -> str:
        """格式化为 SRT 字幕"""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._format_timestamp_srt(seg.start)
            end = self._format_timestamp_srt(seg.end)
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)
    
    def _format_vtt(self, segments) -> str:
        """格式化为 VTT 字幕"""
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = self._format_timestamp_vtt(seg.start)
            end = self._format_timestamp_vtt(seg.end)
            lines.append(f"{start} --> {end}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)
    
    def _format_timestamp_srt(self, seconds: float) -> str:
        """格式化时间戳为 SRT 格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _format_timestamp_vtt(self, seconds: float) -> str:
        """格式化时间戳为 VTT 格式 (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


# ============================================================================
# 全局单例
# ============================================================================

_whisper_manager: Optional[WhisperManager] = None


def get_whisper_manager() -> WhisperManager:
    """获取 Whisper 管理器单例"""
    global _whisper_manager
    if _whisper_manager is None:
        _whisper_manager = WhisperManager()
    return _whisper_manager
