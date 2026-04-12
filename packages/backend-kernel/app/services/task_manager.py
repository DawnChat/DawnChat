"""
长时间运行任务管理器

负责管理异步执行的长时间任务，提供：
- 任务提交和执行
- 任务状态查询
- 任务取消
- 进度更新和推送

设计原则：
- 对 Plugin 透明：SDK 层封装异步等待逻辑
- 智能路由：根据工具元数据自动选择执行策略
- 非阻塞：长任务在后台线程/进程执行，不阻塞事件循环
- 上下文传递：通过 contextvars 让工具函数可以上报进度
"""

import asyncio
import contextvars
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import time
from typing import Any, Awaitable, Callable, Coroutine, Dict, Optional, cast
import uuid

from app.utils.logger import get_logger

logger = get_logger("task_manager")


# ============================================================================
# 上下文变量：用于在任务执行期间传递 task_id
# ============================================================================

# 当前执行上下文中的 task_id
_current_task_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_task_id",
    default=None
)


def get_current_task_id() -> Optional[str]:
    """
    获取当前执行上下文中的 task_id
    
    工具函数可以使用此方法获取当前任务 ID，然后调用 report_progress 上报进度。
    
    Returns:
        task_id 字符串，如果不在任务上下文中则返回 None
    """
    return _current_task_id.get()


def _set_current_task_id(task_id: Optional[str]) -> contextvars.Token:
    """设置当前执行上下文中的 task_id（内部使用）"""
    return _current_task_id.set(task_id)


def _reset_current_task_id(token: contextvars.Token) -> None:
    """重置 task_id 到之前的值（内部使用）"""
    _current_task_id.reset(token)


async def report_progress(progress: float, message: str = "") -> None:
    """
    上报任务进度（供工具函数调用）
    
    这是一个便捷函数，工具函数可以直接调用它来上报进度，
    无需关心 task_id 和 TaskManager 的细节。
    
    Args:
        progress: 进度值 (0.0 - 1.0)
        message: 进度消息（如 "正在转录第 5/10 段..."）
    
    Example:
        from app.services.task_manager import report_progress
        
        async def my_long_task():
            for i in range(10):
                # 执行工作...
                await report_progress(i / 10, f"处理中 {i+1}/10")
    """
    task_id = get_current_task_id()
    if task_id:
        task_manager = get_task_manager()
        await task_manager.update_progress(task_id, progress, message)


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"      # 排队中
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


class TaskIdleTimeoutError(Exception):
    """任务空闲超时"""


@dataclass
class TaskInfo:
    """任务信息"""
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    plugin_id: str
    
    # 状态
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 - 1.0
    progress_message: str = ""
    
    # 结果
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    
    # 时间
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.now)
    last_progress_at: Optional[datetime] = None
    
    # 调度策略
    timeout_seconds: Optional[float] = None
    idle_timeout_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 内部
    _future: Optional[asyncio.Future] = field(default=None, repr=False)
    _runner_task: Optional[asyncio.Task] = field(default=None, repr=False)
    _last_heartbeat_monotonic: float = field(default_factory=time.monotonic, repr=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 API 响应）"""
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat(),
            "last_progress_at": self.last_progress_at.isoformat() if self.last_progress_at else None,
            "error_code": self.error_code,
            "timeout_seconds": self.timeout_seconds,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "metadata": self.metadata,
        }


# 进度回调类型
ProgressCallback = Callable[[str, float, str], Awaitable[None]]


class TaskManager:
    """
    任务管理器（单例）
    
    职责：
    1. 管理长时间运行任务的生命周期
    2. 提供任务提交、查询、取消接口
    3. 在后台线程池执行任务，避免阻塞事件循环
    4. 支持进度更新，通过回调推送到 WebSocket
    """
    
    _instance: Optional['TaskManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 任务存储 {task_id: TaskInfo}
        self._tasks: Dict[str, TaskInfo] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._plugin_limits: Dict[str, asyncio.Semaphore] = {}
        self._global_limit = asyncio.Semaphore(16)
        
        # 进度回调（由 WebSocket 模块注册）
        self._progress_callback: Optional[ProgressCallback] = None
        
        # 锁
        self._lock = asyncio.Lock()
        
        logger.info("TaskManager 初始化完成")
    
    def set_progress_callback(self, callback: ProgressCallback):
        """
        设置进度回调
        
        由 WebSocket 模块调用，用于推送任务进度和结果。
        """
        self._progress_callback = callback
        logger.info("TaskManager 进度回调已设置")
    
    async def submit(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        plugin_id: str,
        executor_func: Callable[..., Awaitable[Any]],
        timeout: Optional[float] = None,
        idle_timeout: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        提交长时间运行任务
        
        Args:
            tool_name: 工具名称
            arguments: 调用参数
            plugin_id: 来源插件 ID
            executor_func: 实际执行函数（异步）
            task_id: 可选，由调用方预先分配的任务 ID（须非空且当前未占用）。
                用于调用方在 submit 返回前与其它子系统（如 PluginLifecycleService._operations）同步登记。
        
        Returns:
            task_id: 任务 ID
        """
        if task_id is not None:
            chosen_id = str(task_id).strip()
            if not chosen_id:
                raise ValueError("task_id must not be empty when provided")
        else:
            chosen_id = str(uuid.uuid4())[:8]

        task = TaskInfo(
            task_id=chosen_id,
            tool_name=tool_name,
            arguments=arguments,
            plugin_id=plugin_id,
            timeout_seconds=timeout,
            idle_timeout_seconds=idle_timeout,
            metadata=metadata or {},
        )

        async with self._lock:
            if chosen_id in self._tasks:
                raise ValueError(f"Task id already exists: {chosen_id}")
            self._tasks[chosen_id] = task

        task_id = chosen_id
        
        logger.info(f"[Task {task_id}] 任务已提交: {tool_name}")
        
        # 创建后台任务执行
        runner_task = asyncio.create_task(self._execute_task(task, executor_func))
        task._runner_task = runner_task
        async with self._lock:
            self._running_tasks[task_id] = runner_task
        
        return task_id
    
    async def _execute_task(
        self,
        task: TaskInfo,
        executor_func: Callable[..., Awaitable[Any]],
    ):
        """执行任务（后台）"""
        task_id = task.task_id
        
        # 设置上下文变量，让工具函数可以获取 task_id 并上报进度
        token = _set_current_task_id(task_id)
        
        try:
            per_plugin_limit = self._plugin_limits.get(task.plugin_id)
            if per_plugin_limit is None:
                per_plugin_limit = asyncio.Semaphore(4)
                self._plugin_limits[task.plugin_id] = per_plugin_limit
            async with self._global_limit, per_plugin_limit:
                # 更新状态为运行中
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                task.updated_at = datetime.now()
                task._last_heartbeat_monotonic = time.monotonic()

                await self._notify_progress(task_id, 0.0, "任务开始执行...")

                logger.info(
                    f"[Task {task_id}] 开始执行 "
                    f"(timeout={task.timeout_seconds}, idle_timeout={task.idle_timeout_seconds})"
                )

                # 执行实际工作
                result = await self._await_with_timeouts(task, executor_func(**task.arguments))

                # 更新状态为完成
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.progress = 1.0
                task.completed_at = datetime.now()
                task.updated_at = datetime.now()

                logger.info(f"[Task {task_id}] 执行完成")

                # 通知完成
                await self._notify_completed(task_id, result)
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.updated_at = datetime.now()
            task.error = "Task cancelled"
            task.error_code = "TASK_CANCELLED"
            logger.info(f"[Task {task_id}] 任务已取消")
            await self._notify_failed(task_id, "任务已取消")
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task execution timed out after {task.timeout_seconds}s"
            task.error_code = "TASK_TIMEOUT"
            task.completed_at = datetime.now()
            task.updated_at = datetime.now()
            logger.warning(f"[Task {task_id}] 任务执行超时")
            await self._notify_failed(task_id, task.error)
        except TaskIdleTimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task idle timeout after {task.idle_timeout_seconds}s without progress"
            task.error_code = "TASK_IDLE_TIMEOUT"
            task.completed_at = datetime.now()
            task.updated_at = datetime.now()
            logger.warning(f"[Task {task_id}] 任务空闲超时")
            await self._notify_failed(task_id, task.error)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.error_code = "TASK_EXECUTION_ERROR"
            task.completed_at = datetime.now()
            task.updated_at = datetime.now()
            logger.error(f"[Task {task_id}] 执行失败: {e}", exc_info=True)
            await self._notify_failed(task_id, str(e))
        
        finally:
            async with self._lock:
                self._running_tasks.pop(task_id, None)
            # 恢复上下文变量
            _reset_current_task_id(token)

    async def _await_with_timeouts(self, task: TaskInfo, awaitable: Awaitable[Any]) -> Any:
        """
        统一处理任务硬超时（timeout）和空闲超时（idle_timeout）。
        """
        runner: asyncio.Future[Any] = asyncio.create_task(
            cast(Coroutine[Any, Any, Any], awaitable)
        )
        task._future = runner
        try:
            loop = asyncio.get_event_loop()
            deadline = loop.time() + task.timeout_seconds if task.timeout_seconds else None
            heartbeat = task._last_heartbeat_monotonic

            while True:
                now = loop.time()
                if deadline and now >= deadline:
                    runner.cancel()
                    raise asyncio.TimeoutError()

                wait_step = 1.0
                if task.idle_timeout_seconds and task.idle_timeout_seconds > 0:
                    # 空闲超时检测需要更细粒度轮询，避免短 idle timeout 被漏判。
                    wait_step = min(wait_step, max(0.05, task.idle_timeout_seconds / 2))
                if deadline:
                    wait_step = min(wait_step, max(0.1, deadline - now))
                if task.idle_timeout_seconds and task.idle_timeout_seconds > 0:
                    wait_step = min(wait_step, max(0.05, task.idle_timeout_seconds / 2))

                try:
                    return await asyncio.wait_for(asyncio.shield(runner), timeout=wait_step)
                except asyncio.TimeoutError:
                    if runner.done():
                        return await runner
                    if task.idle_timeout_seconds and task.idle_timeout_seconds > 0:
                        heartbeat = task._last_heartbeat_monotonic
                        if (time.monotonic() - heartbeat) > task.idle_timeout_seconds:
                            runner.cancel()
                            raise TaskIdleTimeoutError()
                    continue
        finally:
            task._future = None
    
    async def update_progress(
        self,
        task_id: str,
        progress: float,
        message: str = ""
    ):
        """
        更新任务进度
        
        Args:
            task_id: 任务 ID
            progress: 进度值 (0.0 - 1.0)
            message: 进度消息
        """
        task = self._tasks.get(task_id)
        if task:
            task.progress = max(0.0, min(1.0, progress))
            task.progress_message = message
            task.updated_at = datetime.now()
            task.last_progress_at = datetime.now()
            task._last_heartbeat_monotonic = time.monotonic()
            await self._notify_progress(task_id, task.progress, message)
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务信息"""
        return self._tasks.get(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态（用于 API 响应）"""
        task = self._tasks.get(task_id)
        if task:
            return task.to_dict()
        return None
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Returns:
            是否成功取消
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        
        runner = task._runner_task or self._running_tasks.get(task_id)
        if runner and not runner.done():
            runner.cancel()
            logger.info(f"[Task {task_id}] 已发送取消信号")
            return True

        # 任务尚未开始执行时，直接标记取消
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()
        task.error = "Task cancelled before execution"
        task.error_code = "TASK_CANCELLED"
        logger.info(f"[Task {task_id}] 任务已标记取消（未运行）")
        return True
    
    async def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Any]:
        """
        等待任务完成
        
        Args:
            task_id: 任务 ID
            timeout: 超时时间（秒）
        
        Returns:
            任务结果，如果超时或失败返回 None
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        start_time = asyncio.get_event_loop().time()
        
        while task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                return None
            await asyncio.sleep(0.1)
        
        if task.status == TaskStatus.COMPLETED:
            return task.result
        
        return None
    
    def cleanup_old_tasks(self, max_age_seconds: int = 3600):
        """清理过期任务"""
        now = datetime.now()
        expired = []
        
        for task_id, task in self._tasks.items():
            if task.completed_at:
                age = (now - task.completed_at).total_seconds()
                if age > max_age_seconds:
                    expired.append(task_id)
        
        for task_id in expired:
            del self._tasks[task_id]
        
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期任务")
    
    # ========== 通知方法 ==========
    
    async def _notify_progress(self, task_id: str, progress: float, message: str):
        """通知进度更新"""
        if self._progress_callback:
            try:
                await self._progress_callback(task_id, progress, message)
            except Exception as e:
                logger.error(f"进度回调失败: {e}")
    
    async def _notify_completed(self, task_id: str, result: Any):
        """
        通知任务完成
        
        通过调用 progress_callback 触发 TaskAdapter 发送 task_completed 消息。
        TaskAdapter 会检查任务状态并发送正确的消息类型。
        """
        if self._progress_callback:
            try:
                # 触发回调，TaskAdapter 会检查 task.status == COMPLETED 并发送 task_completed
                await self._progress_callback(task_id, 1.0, "任务完成")
            except Exception as e:
                logger.error(f"完成回调失败: {e}")
    
    async def _notify_failed(self, task_id: str, error: str):
        """
        通知任务失败
        
        通过调用 progress_callback 触发 TaskAdapter 发送 task_failed 消息。
        TaskAdapter 会检查任务状态并发送正确的消息类型。
        """
        if self._progress_callback:
            try:
                # 触发回调，TaskAdapter 会检查 task.status == FAILED 并发送 task_failed
                await self._progress_callback(task_id, -1, error)
            except Exception as e:
                logger.error(f"失败回调失败: {e}")


# ============================================================================
# 全局单例
# ============================================================================

_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

