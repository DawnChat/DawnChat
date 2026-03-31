"""
DawnChat - 模型生命周期管理器
负责模型的懒加载、自动卸载、请求排队等功能
让模型加载对用户完全透明
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from app.config import Config
from app.services.llama_server_manager import LlamaServerManager, get_server_manager
from app.services.model_manager import ModelManager, get_model_manager
from app.utils.logger import setup_logger

logger = setup_logger("dawnchat.lifecycle", log_file=Config.LOGS_DIR / "llama.log")


class ModelState(Enum):
    """模型状态"""
    UNLOADED = "unloaded"      # 未加载
    LOADING = "loading"        # 加载中
    LOADED = "loaded"          # 已加载
    UNLOADING = "unloading"    # 卸载中
    ERROR = "error"            # 错误状态


@dataclass
class LoadedModelInfo:
    """已加载模型信息"""
    model_id: str
    model_path: Path
    loaded_at: datetime
    last_used_at: datetime
    context_size: int
    gpu_layers: int


class ModelLifecycleManager:
    """
    模型生命周期管理器
    
    核心功能：
    1. 懒加载 (Lazy Loading): 用户选择模型时不加载，首次 AI 请求时自动触发
    2. 自动卸载 (Auto Unload): 空闲超时后自动停止 llama-server，释放内存/VRAM
    3. 请求排队 (Request Queueing): 加载期间的请求等待，加载完成后自动处理
    
    状态机：
    UNLOADED ──(AI请求)──▶ LOADING ──(健康检查通过)──▶ LOADED
        ▲                                                │
        │                                                │
        └──────────(空闲超时/手动卸载)───────────────────┘
    """
    
    _instance: Optional['ModelLifecycleManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 依赖的管理器
        self._server_manager: LlamaServerManager = get_server_manager()
        self._model_manager: ModelManager = get_model_manager()
        
        # 状态
        self._state = ModelState.UNLOADED
        self._current_model: Optional[LoadedModelInfo] = None
        self._error_message: Optional[str] = None
        
        # 并发控制
        self._loading_lock = asyncio.Lock()
        self._loading_event = asyncio.Event()
        self._loading_event.set()  # 初始状态为已完成
        
        # 自动卸载定时器
        self._unload_task: Optional[asyncio.Task] = None
        self._idle_timeout = Config.LLAMA_SERVER_IDLE_TIMEOUT
        
        logger.info(f"模型生命周期管理器初始化完成 (空闲超时: {self._idle_timeout}秒)")
    
    @property
    def state(self) -> ModelState:
        """获取当前状态"""
        return self._state
    
    @property
    def current_model_id(self) -> Optional[str]:
        """获取当前加载的模型 ID"""
        return self._current_model.model_id if self._current_model else None
    
    async def ensure_model_ready(self, model_id: str) -> bool:
        """
        确保模型已加载（懒加载入口）
        在 AI 请求前调用此方法
        
        Args:
            model_id: 请求的模型 ID（由前端传入）
        
        Returns:
            是否就绪
        """
        # 快速路径：模型已加载且匹配
        if (self._state == ModelState.LOADED and 
            self._current_model and 
            self._current_model.model_id == model_id):
            self._touch()
            logger.debug(f"模型 {model_id} 已就绪（快速路径）")
            return True
        
        # 需要加载或切换模型
        async with self._loading_lock:
            # 双重检查
            if (self._state == ModelState.LOADED and 
                self._current_model and 
                self._current_model.model_id == model_id):
                self._touch()
                return True
            
            # 如果正在加载同一个模型，等待完成
            if (self._state == ModelState.LOADING and 
                self._current_model and 
                self._current_model.model_id == model_id):
                logger.info(f"等待模型 {model_id} 加载完成...")
                return await self._wait_for_loading()
            
            # 如果正在加载其他模型，等待后重试
            if self._state == ModelState.LOADING:
                logger.info(f"等待当前模型加载完成后切换到 {model_id}...")
                await self._wait_for_loading()
                # 递归重试
                return await self.ensure_model_ready(model_id)
            
            # 如果加载了其他模型，先卸载
            if self._state == ModelState.LOADED:
                old_model = self._current_model.model_id if self._current_model else "unknown"
                logger.info(f"卸载当前模型 {old_model} 以切换到 {model_id}")
                await self._unload_current()
            
            # 加载目标模型
            return await self._load_model(model_id)
    
    async def _load_model(self, model_id: str) -> bool:
        """内部：加载模型"""
        logger.info(f"开始加载模型: {model_id}")
        
        # 获取模型路径
        model_path = self._model_manager.get_model_path(model_id)
        if not model_path:
            logger.error(f"模型文件不存在: {model_id} path: {model_path}")
            self._state = ModelState.ERROR
            self._error_message = f"模型文件不存在: {model_id}"
            return False
        
        # 获取模型配置
        model_info = self._model_manager.get_model_info(model_id)
        # 默认使用最大窗口，除非用户自己指定
        context_size = model_info.get("context_length", Config.LLAMA_SERVER_DEFAULT_CONTEXT) if model_info else Config.LLAMA_SERVER_DEFAULT_CONTEXT
        gpu_layers = model_info.get("gpu_layers_default", Config.LLAMA_SERVER_DEFAULT_GPU_LAYERS) if model_info else Config.LLAMA_SERVER_DEFAULT_GPU_LAYERS
        
        logger.info(f"限制上下文大小为 {context_size}")
        
        # 更新状态
        self._state = ModelState.LOADING
        self._loading_event.clear()
        self._current_model = LoadedModelInfo(
            model_id=model_id,
            model_path=model_path,
            loaded_at=datetime.now(),
            last_used_at=datetime.now(),
            context_size=context_size,
            gpu_layers=gpu_layers,
        )
        
        try:
            # 启动 llama-server
            success = await self._server_manager.start_with_model(
                model_path,
                context_size=context_size,
                gpu_layers=gpu_layers
            )
            
            if success:
                self._state = ModelState.LOADED
                self._error_message = None
                
                # 启动自动卸载定时器
                self._start_unload_timer()
                
                logger.info(f"✅ 模型 {model_id} 加载成功")
                return True
            else:
                self._state = ModelState.ERROR
                self._error_message = "llama-server 启动失败"
                self._current_model = None
                logger.error(f"❌ 模型 {model_id} 加载失败")
                return False
                
        except Exception as e:
            logger.error(f"加载模型时发生异常: {e}", exc_info=True)
            self._state = ModelState.ERROR
            self._error_message = str(e)
            self._current_model = None
            return False
        finally:
            self._loading_event.set()
    
    async def _wait_for_loading(self) -> bool:
        """等待当前加载完成"""
        try:
            await asyncio.wait_for(
                self._loading_event.wait(),
                timeout=Config.LLAMA_SERVER_LOADING_TIMEOUT
            )
            return self._state == ModelState.LOADED
        except asyncio.TimeoutError:
            logger.error("等待模型加载超时")
            return False
    
    def _touch(self):
        """更新最后使用时间（重置卸载定时器）"""
        if self._current_model:
            self._current_model.last_used_at = datetime.now()
            # 重启卸载定时器
            self._start_unload_timer()
    
    def _start_unload_timer(self):
        """启动/重置自动卸载定时器"""
        # 取消现有定时器
        if self._unload_task:
            self._unload_task.cancel()
            self._unload_task = None
        
        async def unload_after_idle():
            try:
                await asyncio.sleep(self._idle_timeout)
                
                # 再次检查状态
                if self._state == ModelState.LOADED and self._current_model:
                    idle_seconds = (datetime.now() - self._current_model.last_used_at).total_seconds()
                    if idle_seconds >= self._idle_timeout:
                        logger.info(f"模型 {self._current_model.model_id} 空闲 {int(idle_seconds)} 秒，自动卸载")
                        await self._auto_unload()
            except asyncio.CancelledError:
                pass
        
        self._unload_task = asyncio.create_task(unload_after_idle())
    
    async def _auto_unload(self):
        """自动卸载（空闲超时触发）"""
        if self._state != ModelState.LOADED:
            return
        
        async with self._loading_lock:
            if self._state != ModelState.LOADED:
                return
            await self._unload_current()
    
    async def _unload_current(self):
        """卸载当前模型"""
        if self._unload_task:
            self._unload_task.cancel()
            self._unload_task = None
        
        model_id = self._current_model.model_id if self._current_model else "unknown"
        logger.info(f"卸载模型: {model_id}")
        
        self._state = ModelState.UNLOADING
        
        try:
            await self._server_manager.stop()
        except Exception as e:
            logger.error(f"停止 llama-server 时出错: {e}")
        
        self._current_model = None
        self._state = ModelState.UNLOADED
        logger.info(f"模型 {model_id} 已卸载")
    
    async def unload(self) -> bool:
        """手动卸载当前模型"""
        async with self._loading_lock:
            if self._state == ModelState.UNLOADED:
                return True
            
            if self._state == ModelState.LOADING:
                logger.warning("模型正在加载中，无法卸载")
                return False
            
            await self._unload_current()
            return True
    
    def get_status(self) -> Dict:
        """获取当前状态（供前端查询）"""
        server_status = self._server_manager.get_status()
        
        result = {
            "state": self._state.value,
            "loaded_model": self._current_model.model_id if self._current_model else None,
            "loaded_at": self._current_model.loaded_at.isoformat() if self._current_model else None,
            "last_used_at": self._current_model.last_used_at.isoformat() if self._current_model else None,
            "context_size": self._current_model.context_size if self._current_model else None,
            "gpu_layers": self._current_model.gpu_layers if self._current_model else None,
            "idle_timeout_seconds": self._idle_timeout,
            "error_message": self._error_message,
            "server": server_status,
        }
        
        # 计算空闲时间
        if self._current_model and self._state == ModelState.LOADED:
            idle_seconds = (datetime.now() - self._current_model.last_used_at).total_seconds()
            result["idle_seconds"] = int(idle_seconds)
            result["time_until_unload"] = max(0, int(self._idle_timeout - idle_seconds))
        
        return result
    
    def get_api_base(self) -> Optional[str]:
        """获取当前 llama-server 的 API 基础 URL"""
        if self._state == ModelState.LOADED:
            return self._server_manager.get_api_base()
        return None
    
    async def shutdown(self):
        """关闭管理器（应用退出时调用）"""
        logger.info("关闭模型生命周期管理器...")
        
        if self._unload_task:
            self._unload_task.cancel()
            self._unload_task = None
        
        if self._state in (ModelState.LOADED, ModelState.LOADING):
            await self._server_manager.stop(force=True)
        
        self._state = ModelState.UNLOADED
        self._current_model = None
        logger.info("模型生命周期管理器已关闭")


# 全局单例
_lifecycle_manager: Optional[ModelLifecycleManager] = None


def get_lifecycle_manager() -> ModelLifecycleManager:
    """获取模型生命周期管理器单例"""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = ModelLifecycleManager()
    return _lifecycle_manager

