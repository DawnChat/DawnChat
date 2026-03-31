"""
父进程监控守护模块

监控 Tauri 主进程的存活状态，当父进程消失时触发 Python 后端的优雅关闭。
这是双向进程生命周期管理的 "向上监控" 部分。

工作原理：
1. 启动时从环境变量 DAWNCHAT_PARENT_PID 读取 Tauri 进程的 PID
2. 后台协程每 2 秒检查父进程是否存在
3. 如果父进程不存在，向自身发送 SIGTERM 信号，触发 FastAPI 的 lifespan shutdown
"""

import asyncio
import os
import signal
import sys
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger("parent_watcher")

# 检查间隔（秒）
CHECK_INTERVAL = 2

# 全局任务引用，用于取消
_watcher_task: Optional[asyncio.Task] = None


def _is_process_alive(pid: int) -> bool:
    """
    检查进程是否存活（跨平台）
    
    使用 os.kill(pid, 0) 发送空信号：
    - 如果进程存在，返回 True
    - 如果进程不存在，抛出 OSError，返回 False
    
    Args:
        pid: 要检查的进程 ID
        
    Returns:
        进程是否存活
    """
    if sys.platform == "win32":
        # Windows 需要特殊处理
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        # Unix/macOS: 使用 kill 信号 0
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


async def watch_parent_process() -> None:
    """
    监控父进程，父进程消失则触发 graceful shutdown
    
    这个协程会持续运行，直到：
    1. 检测到父进程消失，发送 SIGTERM
    2. 被外部取消（如应用正常关闭）
    """
    parent_pid_str = os.environ.get("DAWNCHAT_PARENT_PID", "")
    
    if not parent_pid_str:
        logger.info("未设置 DAWNCHAT_PARENT_PID 环境变量，跳过父进程监控（开发模式）")
        return
    
    try:
        parent_pid = int(parent_pid_str)
    except ValueError:
        logger.error(f"无效的 DAWNCHAT_PARENT_PID 值: {parent_pid_str}")
        return
    
    if parent_pid <= 0:
        logger.warning(f"无效的父进程 PID: {parent_pid}，跳过监控")
        return
    
    logger.info(f"🔭 开始监控父进程 PID: {parent_pid}，检查间隔: {CHECK_INTERVAL}s")
    
    # 首次检查，确认父进程存在
    if not _is_process_alive(parent_pid):
        logger.error(f"父进程 {parent_pid} 在启动时就不存在，立即退出")
        os.kill(os.getpid(), signal.SIGTERM)
        return
    
    try:
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            
            if not _is_process_alive(parent_pid):
                logger.warning(f"⚠️ 父进程 {parent_pid} 已退出，触发 graceful shutdown...")
                
                # 发送 SIGTERM 给自己，触发 FastAPI lifespan 的 shutdown 流程
                # 这样可以确保所有清理逻辑都被正确执行
                if sys.platform == "win32":
                    # Windows 没有 SIGTERM，使用 SIGINT
                    os.kill(os.getpid(), signal.SIGINT)
                else:
                    os.kill(os.getpid(), signal.SIGTERM)
                break
                
    except asyncio.CancelledError:
        logger.debug("父进程监控任务被取消")
        raise


def start_parent_watcher() -> Optional[asyncio.Task]:
    """
    启动父进程监控任务
    
    Returns:
        监控任务对象，如果不需要监控则返回 None
    """
    global _watcher_task
    
    if _watcher_task is not None and not _watcher_task.done():
        logger.warning("父进程监控任务已在运行")
        return _watcher_task
    
    _watcher_task = asyncio.create_task(watch_parent_process())
    return _watcher_task


def stop_parent_watcher() -> None:
    """停止父进程监控任务"""
    global _watcher_task
    
    if _watcher_task is not None and not _watcher_task.done():
        _watcher_task.cancel()
        logger.debug("父进程监控任务已请求取消")
    
    _watcher_task = None

