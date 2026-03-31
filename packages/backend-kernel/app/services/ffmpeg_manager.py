"""
FFmpeg 组件管理器

负责 FFmpeg 二进制文件的下载、安装、校验和路径管理。
遵循“用户侧载”模式，从 SourceForge 下载 GPL-Lite 版本。
"""

import os
import platform
import subprocess
import tarfile
import time
from typing import Callable, Dict, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("services.ffmpeg")

# 定义组件存放路径 (由 Host 分配的数据目录)
# 使用 Config 中定义的统一用户数据目录，避免分散
FFMPEG_DIR = Config.FFMPEG_DIR
BIN_DIR = FFMPEG_DIR / "bin"
FFMPEG_EXE = BIN_DIR / ("ffmpeg.exe" if os.name == 'nt' else "ffmpeg")
FFPROBE_EXE = BIN_DIR / ("ffprobe.exe" if os.name == 'nt' else "ffprobe")
DOWNLOAD_CACHE_FILE = FFMPEG_DIR / ".download_cache"

# SourceForge mirror candidates for Asia-friendly fallback.
SOURCEFORGE_MIRRORS = [
    "",  # official auto mirror selection
    "nchc",   # Taiwan
    "jaist",  # Japan
    "kumisystems",
    "netix",
    "versaweb",
]

def get_download_url() -> Optional[str]:
    """获取对应平台的下载直链"""
    system = platform.system()
    
    if system == "Windows":
        # Windows x86_64
        return "https://sourceforge.net/projects/avbuild/files/windows-desktop/ffmpeg-8.0-windows-desktop-vs2022-gpl-lite.7z/download"
    elif system == "Darwin":
        # macOS Universal / x86_64 / arm64 (avbuild 通常提供 universal 或者特定架构)
        # 这里使用 avbuild 的 macOS 构建
        return "https://sourceforge.net/projects/avbuild/files/macOS/ffmpeg-8.0-macOS-gpl-lite.tar.xz/download"
    elif system == "Linux":
        # Linux x86_64
        return "https://sourceforge.net/projects/avbuild/files/linux/ffmpeg-8.0-linux-clang-gpl-lite.tar.xz/download"
        
    return None


def _load_last_success_url() -> Optional[str]:
    try:
        if DOWNLOAD_CACHE_FILE.exists():
            data = DOWNLOAD_CACHE_FILE.read_text(encoding="utf-8").strip()
            return data or None
    except Exception:
        pass
    return None


def _save_last_success_url(url: str) -> None:
    try:
        DOWNLOAD_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        DOWNLOAD_CACHE_FILE.write_text(url, encoding="utf-8")
    except Exception as e:
        logger.warning(f"保存 FFmpeg 成功下载源失败: {e}")


def _with_sourceforge_mirror(url: str, mirror: str) -> str:
    if not mirror:
        return url
    parts = urlsplit(url)
    query = urlencode({"use_mirror": mirror})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def resolve_download_candidates() -> list[str]:
    base = get_download_url()
    if not base:
        return []

    candidates = [_with_sourceforge_mirror(base, m) for m in SOURCEFORGE_MIRRORS]
    sticky = _load_last_success_url()
    if sticky and sticky in candidates:
        candidates = [sticky] + [c for c in candidates if c != sticky]
    return candidates


def _probe_url(url: str, timeout_seconds: float = 2.5) -> tuple[bool, int, Optional[str]]:
    started = time.perf_counter()
    try:
        with requests.get(
            url,
            stream=True,
            allow_redirects=True,
            timeout=(min(timeout_seconds, 2.0), timeout_seconds),
        ) as resp:
            resp.raise_for_status()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return True, elapsed_ms, None
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return False, elapsed_ms, str(e)


def rank_candidates_by_probe(candidates: list[str]) -> list[str]:
    if not candidates:
        return []

    reachable: list[tuple[int, int, str]] = []
    unreachable: list[tuple[int, str]] = []

    for idx, url in enumerate(candidates):
        ok, latency_ms, error = _probe_url(url)
        if ok:
            logger.info(f"FFmpeg 下载源可达: {url} ({latency_ms}ms)")
            reachable.append((latency_ms, idx, url))
        else:
            logger.warning(f"FFmpeg 下载源探测失败: {url} ({latency_ms}ms) - {error}")
            unreachable.append((idx, url))

    reachable.sort(key=lambda x: (x[0], x[1]))
    ordered = [url for _, _, url in reachable] + [url for _, url in sorted(unreachable, key=lambda x: x[0])]
    return ordered

def check_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用"""
    return FFMPEG_EXE.exists() and os.access(FFMPEG_EXE, os.X_OK)

def get_ffmpeg_path() -> str:
    """获取 FFmpeg 可执行文件路径"""
    return str(FFMPEG_EXE)

def get_ffprobe_path() -> str:
    """获取 FFprobe 可执行文件路径"""
    return str(FFPROBE_EXE)

def inject_ffmpeg_env(env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    target = env if env is not None else os.environ

    ffmpeg_dir = Config.FFMPEG_DIR
    bin_dir = ffmpeg_dir / "bin"
    lib_dir = ffmpeg_dir / "lib"

    if bin_dir.exists():
        target["PATH"] = f"{str(bin_dir)}{os.pathsep}{target.get('PATH', '')}"

    if lib_dir.exists():
        system = platform.system()
        if system == "Darwin":
            target["DYLD_LIBRARY_PATH"] = f"{str(lib_dir)}{os.pathsep}{target.get('DYLD_LIBRARY_PATH', '')}"
            target["DYLD_FALLBACK_LIBRARY_PATH"] = (
                f"{str(lib_dir)}{os.pathsep}{target.get('DYLD_FALLBACK_LIBRARY_PATH', '')}"
            )
        elif system == "Linux":
            target["LD_LIBRARY_PATH"] = f"{str(lib_dir)}{os.pathsep}{target.get('LD_LIBRARY_PATH', '')}"

    return dict(target) if env is not None else os.environ.copy()

def setup_ffmpeg(ui_callback: Optional[Callable[[str, int], None]] = None) -> bool:
    """
    执行下载安装流程
    
    Args:
        ui_callback: 进度回调函数 callback(message, progress_percent)
    
    Returns:
        bool: 是否安装成功
    """
    def report(msg, progress):
        logger.info(f"{msg} ({progress}%)")
        if ui_callback:
            ui_callback(msg, progress)

    candidates = rank_candidates_by_probe(resolve_download_candidates())
    if not candidates:
        report("当前系统不支持自动下载 FFmpeg", -1)
        return False
    
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    LIB_DIR = FFMPEG_DIR / "lib"
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    
    temp_tar = BIN_DIR / "temp_ffmpeg.tar.xz"
    try:
        for idx, url in enumerate(candidates):
            try:
                report(f"正在下载视频组件 (线路 {idx + 1}/{len(candidates)})...", 0)
                with requests.get(url, stream=True) as r:
                    r.raise_for_status()
                    total_length = int(r.headers.get('content-length', 0))
                    dl = 0
                    with open(temp_tar, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            dl += len(chunk)
                            f.write(chunk)
                            if total_length > 0 and dl % (1024 * 1024) < 8192:
                                percent = int((dl / total_length) * 80)
                                report("正在下载视频组件...", percent)

                report("正在解压组件...", 85)
                with tarfile.open(temp_tar, "r:xz") as tar:
                    for member in tar.getmembers():
                        if member.name.endswith("/ffmpeg") or member.name.endswith("ffmpeg.exe") or \
                           member.name.endswith("/ffprobe") or member.name.endswith("ffprobe.exe"):
                            member.name = os.path.basename(member.name)
                            tar.extract(member, path=BIN_DIR)
                            continue

                        if "/lib/" in member.name:
                            if member.name.endswith("/lib/"):
                                continue
                            member.name = os.path.basename(member.name)
                            if member.name:
                                tar.extract(member, path=LIB_DIR)

                if platform.system() == "Darwin":
                    report("正在配置权限...", 95)
                    if FFMPEG_EXE.exists():
                        st = os.stat(FFMPEG_EXE)
                        os.chmod(FFMPEG_EXE, st.st_mode | 0o111)
                        subprocess.run(
                            ["xattr", "-d", "com.apple.quarantine", str(FFMPEG_EXE)],
                            check=False,
                            stderr=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                        )

                    if FFPROBE_EXE.exists():
                        st = os.stat(FFPROBE_EXE)
                        os.chmod(FFPROBE_EXE, st.st_mode | 0o111)
                        subprocess.run(
                            ["xattr", "-d", "com.apple.quarantine", str(FFPROBE_EXE)],
                            check=False,
                            stderr=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                        )

                _save_last_success_url(url)
                report("视频组件安装完成", 100)
                return True

            except Exception as e:
                logger.warning(f"FFmpeg 下载线路失败: {url} - {e}")
                if idx == len(candidates) - 1:
                    report(f"安装失败: {str(e)}", -1)
                    logger.error(f"FFmpeg 安装失败: {e}", exc_info=True)
                    return False
    finally:
        # 清理临时文件
        if temp_tar.exists():
            try:
                os.remove(temp_tar)
            except OSError:
                pass

    return False
