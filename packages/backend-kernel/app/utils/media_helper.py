"""
FFmpeg 辅助工具类

封装 ffmpeg-python 的核心操作，屏蔽底层细节。
同时提供 PySceneDetect 场景检测能力。
"""

import importlib.util
import os
from typing import Any, Dict, List, Optional, Tuple

import ffmpeg

from app.services.ffmpeg_manager import check_ffmpeg_available, get_ffmpeg_path, get_ffprobe_path
from app.utils.logger import get_logger

logger = get_logger("utils.media")

# Scene detection imports (lazy loaded)
_scenedetect_available = None

def run_ffmpeg(stream_spec: Any) -> Tuple[bytes, bytes]:
    """
    执行 FFmpeg 任务的统一入口
    
    Args:
        stream_spec: ffmpeg-python 构建的流对象
        
    Returns:
        (stdout, stderr): 执行输出
        
    Raises:
        FileNotFoundError: FFmpeg 未安装
        ffmpeg.Error: 执行出错
    """
    # 1. 检查二进制文件是否存在
    if not check_ffmpeg_available():
        raise FileNotFoundError(f"FFmpeg binary not found at {get_ffmpeg_path()}")
    
    # 2. 执行
    ffmpeg_binary = get_ffmpeg_path()
    
    try:
        out, err = (
            ffmpeg
            .run(
                stream_spec, 
                cmd=ffmpeg_binary, 
                overwrite_output=True,
                capture_stdout=True, 
                capture_stderr=True
            )
        )
        return out, err
    except ffmpeg.Error as e:
        # 打印错误日志，方便调试
        error_log = e.stderr.decode('utf8') if e.stderr else "Unknown error"
        logger.error(f"FFmpeg Error: {error_log}")
        raise e

def extract_frames_for_llm(video_path: str, output_folder: str, fps: int = 1) -> int:
    """
    每秒抽取一帧，保存为低质量 JPEG (节省 LLM Token 和 带宽)
    
    Args:
        video_path: 视频文件路径
        output_folder: 输出目录
        fps: 每秒抽帧数
        
    Returns:
        int: 抽取的帧数
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    # 确保输出目录存在
    os.makedirs(output_folder, exist_ok=True)
    
    # 相当于: ffmpeg -i video.mp4 -vf fps=1 -q:v 5 out_%04d.jpg
    stream = (
        ffmpeg
        .input(video_path)
        .filter('fps', fps=fps)
        .output(
            os.path.join(output_folder, 'frame_%04d.jpg'), 
            **{'q:v': 5}       # 参数：质量等级 5 (1-31, 1最好)
        )
    )
    
    run_ffmpeg(stream)
    
    # 统计生成的文件数
    count = len([name for name in os.listdir(output_folder) if name.endswith(".jpg")])
    logger.info(f"抽帧完成: {count} frames extracted to {output_folder}")
    return count


def extract_frame_at_timestamp(
    video_path: str,
    output_path: str,
    timestamp: float,
    quality: int = 2,
) -> str:
    """
    在指定时间戳提取单帧（高效）。
    
    使用 FFmpeg 的 -ss 快速定位 + -frames:v 1 单帧提取，
    比 fps 全量抽帧效率高得多。
    
    Args:
        video_path: 视频文件路径
        output_path: 输出图片路径（建议 .jpg）
        timestamp: 时间戳（秒）
        quality: JPEG 质量 (1-31, 1最好, 默认2)
        
    Returns:
        str: 输出路径
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 使用 -ss 在 -i 之前进行快速定位（input seeking）
    # 相当于: ffmpeg -ss 10.5 -i video.mp4 -frames:v 1 -q:v 2 output.jpg
    stream = (
        ffmpeg
        .input(video_path, ss=timestamp)
        .output(
            output_path,
            vframes=1,           # 只提取1帧
            **{'q:v': quality}   # JPEG 质量
        )
    )
    
    run_ffmpeg(stream)
    logger.info(f"帧提取完成: {output_path} (timestamp={timestamp:.2f}s)")
    return output_path


def extract_frames_at_timestamps(
    video_path: str,
    output_dir: str,
    timestamps: list,
    quality: int = 2,
) -> list:
    """
    在多个指定时间戳提取帧（批量高效版本）。
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        timestamps: 时间戳列表（秒）
        quality: JPEG 质量 (1-31, 1最好, 默认2)
        
    Returns:
        list: 成功提取的输出路径列表
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    for i, ts in enumerate(timestamps):
        output_path = os.path.join(output_dir, f"frame_{i:04d}_{ts:.2f}s.jpg")
        try:
            extract_frame_at_timestamp(video_path, output_path, ts, quality)
            results.append(output_path)
        except Exception as e:
            logger.warning(f"Failed to extract frame at {ts:.2f}s: {e}")
            continue
    
    logger.info(f"批量帧提取完成: {len(results)}/{len(timestamps)} frames")
    return results

def create_summary_video(image_path: str, audio_path: str, output_path: str) -> str:
    """
    合成视频：静态图 + 音频 -> MP4 (H.264)
    
    Args:
        image_path: 图片路径
        audio_path: 音频路径
        output_path: 输出视频路径
        
    Returns:
        str: 输出路径
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # 输入流
    input_video = ffmpeg.input(image_path, loop=1) # loop=1 表示图片无限循环
    input_audio = ffmpeg.input(audio_path)
    
    stream = ffmpeg.output(
        input_video,
        input_audio,
        output_path,
        
        # --- 编码参数 ---
        vcodec='libx264',   # 使用 H.264 (因为下载的是 GPL 版)
        acodec='aac',       # 音频使用 AAC
        pix_fmt='yuv420p',  # 必须设置，否则某些播放器无法播放
        shortest=None,      # 以最短的流（音频）为结束点
        
        # --- 性能优化 ---
        preset='fast',      # 编码速度
        crf=23,             # 视频质量 (18-28 是常用范围)
        tune='stillimage'   # 针对静态图的优化参数
    )
    
    run_ffmpeg(stream)
    logger.info(f"视频生成完毕: {output_path}")
    return output_path

def get_video_info(video_path: str) -> Optional[Dict[str, Any]]:
    """获取视频信息"""
    ffprobe_binary = get_ffprobe_path()
    
    if not os.path.exists(ffprobe_binary):
        logger.warning("ffprobe not found")
        return None
        
    try:
        # 指定 cmd 参数
        return ffmpeg.probe(video_path, cmd=ffprobe_binary)
    except ffmpeg.Error as e:
        logger.error(f"Probe failed: {e.stderr.decode('utf8') if e.stderr else ''}")
        return None


def get_media_info(media_path: str) -> Dict[str, Any]:
    """
    获取媒体文件的元数据信息
    
    Args:
        media_path: 媒体文件路径（音频或视频）
        
    Returns:
        包含媒体信息的字典：
        - duration: 时长（秒）
        - format: 格式名称
        - size: 文件大小（字节）
        - has_video: 是否包含视频流
        - has_audio: 是否包含音频流
        - video_codec: 视频编码（如有）
        - audio_codec: 音频编码（如有）
        - width: 视频宽度（如有）
        - height: 视频高度（如有）
        - sample_rate: 音频采样率（如有）
        - channels: 音频声道数（如有）
    """
    if not os.path.exists(media_path):
        raise FileNotFoundError(f"Media file not found: {media_path}")
    
    ffprobe_binary = get_ffprobe_path()
    if not os.path.exists(ffprobe_binary):
        raise FileNotFoundError(f"ffprobe not found at {ffprobe_binary}")
    
    try:
        probe_data = ffmpeg.probe(media_path, cmd=ffprobe_binary)
    except ffmpeg.Error as e:
        error_msg = e.stderr.decode('utf8') if e.stderr else 'Unknown error'
        raise RuntimeError(f"Failed to probe media file: {error_msg}")
    
    # 解析格式信息
    format_info = probe_data.get('format', {})
    streams = probe_data.get('streams', [])
    
    # 查找视频和音频流
    video_stream = None
    audio_stream = None
    for stream in streams:
        codec_type = stream.get('codec_type')
        if codec_type == 'video' and video_stream is None:
            video_stream = stream
        elif codec_type == 'audio' and audio_stream is None:
            audio_stream = stream
    
    result = {
        'duration': float(format_info.get('duration', 0)),
        'format': format_info.get('format_name', 'unknown'),
        'format_long_name': format_info.get('format_long_name', ''),
        'size': int(format_info.get('size', 0)),
        'bit_rate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None,
        'has_video': video_stream is not None,
        'has_audio': audio_stream is not None,
    }
    
    # 添加视频流信息
    if video_stream:
        result['video_codec'] = video_stream.get('codec_name')
        result['width'] = video_stream.get('width')
        result['height'] = video_stream.get('height')
        # 计算帧率
        r_frame_rate = video_stream.get('r_frame_rate', '0/1')
        if '/' in r_frame_rate:
            num, den = r_frame_rate.split('/')
            result['fps'] = float(num) / float(den) if float(den) != 0 else 0
        else:
            result['fps'] = float(r_frame_rate) if r_frame_rate else 0
    
    # 添加音频流信息
    if audio_stream:
        result['audio_codec'] = audio_stream.get('codec_name')
        result['sample_rate'] = int(audio_stream.get('sample_rate', 0)) if audio_stream.get('sample_rate') else None
        result['channels'] = audio_stream.get('channels')
    
    logger.info(f"媒体信息获取完成: {media_path}, duration={result['duration']:.2f}s")
    return result


def extract_audio_from_video(
    video_path: str,
    output_path: str,
    sample_rate: int = 16000,
    channels: int = 1,
    audio_format: str = "wav"
) -> str:
    """
    从视频文件中提取音频
    
    Args:
        video_path: 视频文件路径
        output_path: 输出音频文件路径
        sample_rate: 采样率（默认 16000，适合 ASR）
        channels: 声道数（默认 1，单声道）
        audio_format: 输出格式（默认 wav）
        
    Returns:
        str: 输出文件路径
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 构建 ffmpeg 命令
    # 相当于: ffmpeg -i video.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav
    stream = (
        ffmpeg
        .input(video_path)
        .output(
            output_path,
            vn=None,              # 不包含视频
            acodec='pcm_s16le' if audio_format == 'wav' else 'libmp3lame',
            ar=sample_rate,       # 采样率
            ac=channels,          # 声道数
        )
    )
    
    run_ffmpeg(stream)
    logger.info(f"音频提取完成: {output_path} (sr={sample_rate}, ch={channels})")
    return output_path


def normalize_audio(
    audio_path: str,
    output_path: str,
    target_loudness: float = -23.0
) -> str:
    """
    音频响度标准化（EBU R128）
    
    Args:
        audio_path: 输入音频文件路径
        output_path: 输出音频文件路径
        target_loudness: 目标响度（LUFS），默认 -23 LUFS（EBU 标准）
        
    Returns:
        str: 输出文件路径
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    
    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 使用 loudnorm 滤镜进行响度标准化
    # 相当于: ffmpeg -i input.wav -af loudnorm=I=-23 output.wav
    stream = (
        ffmpeg
        .input(audio_path)
        .filter('loudnorm', I=target_loudness)
        .output(output_path)
    )
    
    run_ffmpeg(stream)
    logger.info(f"音频标准化完成: {output_path} (loudness={target_loudness} LUFS)")
    return output_path


# =============================================================================
# Scene Detection (PySceneDetect)
# =============================================================================

def check_scenedetect_available() -> bool:
    """Check if PySceneDetect is available."""
    global _scenedetect_available
    if _scenedetect_available is None:
        _scenedetect_available = importlib.util.find_spec("scenedetect") is not None
    return _scenedetect_available


def detect_scenes(
    video_path: str,
    threshold: float = 27.0,
    min_scene_len: int = 15,
) -> List[Dict[str, Any]]:
    """
    Detect scene boundaries in video using PySceneDetect.
    
    Uses ContentDetector to find significant changes in video content.
    
    Args:
        video_path: Path to video file
        threshold: Content detection threshold (default: 27.0, higher = fewer scenes)
        min_scene_len: Minimum scene length in frames (default: 15)
        
    Returns:
        List of scene dicts with:
        - scene_id: Scene index (0-based)
        - start_time: Start time in seconds
        - end_time: End time in seconds
        - duration: Duration in seconds
        - start_frame: Start frame number
        - end_frame: End frame number
    
    Raises:
        ImportError: If PySceneDetect not installed
        FileNotFoundError: If video file not found
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    if not check_scenedetect_available():
        raise ImportError("PySceneDetect is not installed. Install with: pip install scenedetect[opencv]")
    
    from scenedetect import ContentDetector, detect
    
    logger.info(f"开始场景检测: {video_path} (threshold={threshold})")
    
    # Detect scenes
    scene_list = detect(
        video_path,
        ContentDetector(threshold=threshold, min_scene_len=min_scene_len),
    )
    
    # Convert to dict list
    scenes = []
    for i, scene in enumerate(scene_list):
        start_time = scene[0].get_seconds()
        end_time = scene[1].get_seconds()
        scenes.append({
            "scene_id": i,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "start_frame": scene[0].get_frames(),
            "end_frame": scene[1].get_frames(),
        })
    
    logger.info(f"场景检测完成: {len(scenes)} scenes detected")
    return scenes


def detect_scenes_with_keyframes(
    video_path: str,
    output_dir: str,
    threshold: float = 27.0,
    min_scene_len: int = 15,
    frames_per_scene: int = 1,
) -> Dict[str, Any]:
    """
    Detect scenes and extract keyframes in one operation.
    
    Combines scene detection with efficient keyframe extraction at scene midpoints.
    
    Args:
        video_path: Path to video file
        output_dir: Directory to save keyframes
        threshold: Scene detection threshold
        min_scene_len: Minimum scene length in frames
        frames_per_scene: Number of keyframes per scene (default: 1)
        
    Returns:
        Dict with:
        - scenes: List of scene dicts (with keyframe_paths added)
        - total_keyframes: Total number of extracted keyframes
    """
    # Step 1: Detect scenes
    scenes = detect_scenes(video_path, threshold, min_scene_len)
    
    if not scenes:
        return {"scenes": [], "total_keyframes": 0}
    
    # Step 2: Calculate timestamps for keyframe extraction
    timestamps = []
    for scene in scenes:
        if frames_per_scene == 1:
            # Single frame at midpoint
            midpoint = scene["start_time"] + scene["duration"] / 2
            timestamps.append(midpoint)
        else:
            # Multiple frames evenly distributed
            step = scene["duration"] / (frames_per_scene + 1)
            for i in range(1, frames_per_scene + 1):
                timestamps.append(scene["start_time"] + step * i)
    
    # Step 3: Extract keyframes
    keyframe_paths = extract_frames_at_timestamps(video_path, output_dir, timestamps)
    
    # Step 4: Assign keyframes to scenes
    idx = 0
    for scene in scenes:
        scene["keyframe_paths"] = []
        for _ in range(frames_per_scene):
            if idx < len(keyframe_paths):
                scene["keyframe_paths"].append(keyframe_paths[idx])
                idx += 1
    
    return {
        "scenes": scenes,
        "total_keyframes": len(keyframe_paths),
    }
