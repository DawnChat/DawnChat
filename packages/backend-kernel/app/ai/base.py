"""
DawnChat - AI 适配层基础接口

设计原则：
1. AIProvider：统一的 AI 调用接口（无状态）
2. LocalModelManager：本地模型管理接口（有状态，仅 Ollama）
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from app.config import Config

_THINK_OPEN_RE = re.compile(r"<\s*(think|analysis|thought)\s*>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"<\s*/\s*(think|analysis|thought)\s*>", re.IGNORECASE)
_THINK_BLOCK_RE = re.compile(r"<\s*(think|analysis|thought)\s*>[\s\S]*?<\s*/\s*\1\s*>", re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    close_match = _THINK_CLOSE_RE.search(cleaned)
    open_match = _THINK_OPEN_RE.search(cleaned)
    if close_match and (not open_match or close_match.start() < open_match.start()):
        cleaned = cleaned[close_match.end():]
        open_match = _THINK_OPEN_RE.search(cleaned)
    if open_match and not _THINK_CLOSE_RE.search(cleaned, open_match.end()):
        cleaned = cleaned[:open_match.start()]
    return cleaned.strip()


def _strip_tool_calls_block(text: str) -> str:
    if not text:
        return ""
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return text
        snippet = m.group(0)
        if "tool_calls" in snippet or "tool_call" in snippet:
            try:
                obj = json.loads(snippet)
                if isinstance(obj, dict) and ("tool_calls" in obj or "tool_call" in obj):
                    return (text[:m.start()] + text[m.end():]).strip()
            except Exception:
                return (text[:m.start()] + text[m.end():]).strip()
    except Exception:
        return text
    return text


class _ThinkStreamFilter:
    def __init__(self) -> None:
        self.buffer = ""
        self.in_think = False
        self._open_tail = max(len("<think>"), len("<analysis>"), len("<thought>")) - 1
        self._close_tail = max(len("</think>"), len("</analysis>"), len("</thought>")) - 1

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.buffer += chunk
        out: list[str] = []
        while True:
            if self.in_think:
                m = _THINK_CLOSE_RE.search(self.buffer)
                if not m:
                    if len(self.buffer) > self._close_tail:
                        self.buffer = self.buffer[-self._close_tail:]
                    return "".join(out)
                self.buffer = self.buffer[m.end():]
                self.in_think = False
                continue
            open_match = _THINK_OPEN_RE.search(self.buffer)
            close_match = _THINK_CLOSE_RE.search(self.buffer)
            if close_match and (not open_match or close_match.start() < open_match.start()):
                self.buffer = self.buffer[close_match.end():]
                continue
            if not open_match:
                if len(self.buffer) > self._open_tail:
                    out.append(self.buffer[:-self._open_tail])
                    self.buffer = self.buffer[-self._open_tail:]
                return "".join(out)
            if open_match.start() > 0:
                out.append(self.buffer[:open_match.start()])
            self.buffer = self.buffer[open_match.end():]
            self.in_think = True

    def flush(self) -> str:
        if self.in_think:
            self.buffer = ""
            return ""
        remaining = self.buffer
        self.buffer = ""
        return remaining


class ServiceStatus(Enum):
    """服务状态（仅用于有状态的本地服务，如 Ollama）"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class Message:
    """
    聊天消息
    
    content 支持两种格式：
    1. 纯文本: str
    2. 多模态内容: List[Dict[str, Any]]（符合 OpenAI Vision API 标准）
       例如: [
           {"type": "text", "text": "请分析这个图片"},
           {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
       ]
    """
    role: str  # system, user, assistant, tool
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class CompletionRequest:
    """补全请求"""
    messages: List[Message]
    model: str
    temperature: float = 0.7
    max_tokens: int = Config.TokenBudget.MAX_LIMIT
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    context_length: Optional[int] = None
    provider_options: Optional[Dict[str, Any]] = None


@dataclass
class CompletionResponse:
    """补全响应"""
    content: str
    model: str
    finish_reason: str
    usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    size: int  # 字节
    digest: str
    modified_at: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class HealthStatus:
    """健康状态"""
    is_healthy: bool
    status: ServiceStatus
    message: str
    details: Optional[Dict[str, Any]] = None


class AIProvider(ABC):
    """
    AI 提供商抽象基类
    
    职责：提供统一的 AI 调用接口
    特点：无状态、纯调用层
    实现：LiteLLMProvider（支持 100+ LLM APIs）
    """
    
    @abstractmethod
    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """
        获取 AI 补全（非流式）
        
        Args:
            request: 补全请求
            
        Returns:
            补全响应
        """
        pass
    
    @abstractmethod
    def get_completion_stream(
        self, 
        request: CompletionRequest
    ) -> AsyncIterator[str]:
        """
        获取 AI 补全（流式）
        
        Args:
            request: 补全请求
            
        Yields:
            生成的文本片段
        """
        pass
    

class LocalModelManager(ABC):
    """
    本地模型管理接口
    
    职责：管理本地 AI 服务（如 Ollama）
    包括：进程管理、模型下载/删除、健康检查
    实现：OllamaManager
    """
    
    @abstractmethod
    async def initialize(self) -> bool:
        """初始化服务（启动进程）"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> bool:
        """关闭服务（停止进程）"""
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """健康检查"""
        pass
    
    @abstractmethod
    def get_status(self) -> ServiceStatus:
        """获取当前状态"""
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """是否就绪"""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """列出已安装的模型"""
        pass
    
    @abstractmethod
    async def pull_model(self, model_name: str) -> AsyncIterator[Dict[str, Any]]:
        """拉取/下载模型（流式返回进度）"""
        pass
    
    @abstractmethod
    async def delete_model(self, model_name: str) -> bool:
        """删除模型"""
        pass
