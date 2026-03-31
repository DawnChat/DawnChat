"""
DawnChat - AI 服务路由

职责：提供统一的 AI 能力接口（通过 LiteLLM）

支持的 AI 能力：
1. Completions（文本生成）- 支持本地和云端模型
2. Embeddings（向量化）- 支持文本向量化
3. Image Generation（图像生成）- 待实现
4. Audio Transcription（语音转文字）- 待实现
5. Text-to-Speech（文字转语音）- 待实现

支持的模型：
- 云端模型：OpenAI, Anthropic, Google Gemini, Azure 等 100+ APIs
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai import CompletionRequest, LiteLLMProvider, Message
from app.config import Config
from app.utils.logger import api_logger as logger

# 创建路由器
router = APIRouter()


# ============ 请求/响应模型 ============

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """聊天补全请求"""
    messages: List[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = Config.TokenBudget.MAX_LIMIT
    stream: bool = False
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    context_length: Optional[int] = None


class EmbeddingRequest(BaseModel):
    """向量化请求"""
    input: str | List[str]  # 支持单个文本或文本列表
    model: Optional[str] = None  # 例如: openai:text-embedding-3-small


# ============ 全局单例 ============

_litellm_provider = None


def get_ai_provider():
    """获取统一的 AI Provider（LiteLLM）"""
    global _litellm_provider
    if _litellm_provider is None:
        _litellm_provider = LiteLLMProvider()
    return _litellm_provider


# ============ AI 调用端点 ============

@router.post("/chat/completions")
async def chat_completion(request: ChatCompletionRequest):
    """
    聊天补全端点（统一通过 LiteLLM）
    
    支持：
    - 流式和非流式调用
    - 云端模型（OpenAI, Anthropic等）
    
    模型命名规范：
    - openai:gpt-4 -> OpenAI 模型
    - anthropic:claude-3-opus -> Anthropic 模型
    - gemini:gemini-pro -> Google Gemini 模型
    """
    try:
        # 统一通过 LiteLLM 进行 AI 调用
        provider = get_ai_provider()
        
        # 转换消息格式
        messages = [Message(role=msg.role, content=msg.content) for msg in request.messages]
        
        completion_request = CompletionRequest(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=request.stream,
            top_p=request.top_p,
            top_k=request.top_k,
            presence_penalty=request.presence_penalty,
            frequency_penalty=request.frequency_penalty,
            stop=request.stop,
            context_length=request.context_length
        )
        
        # 流式响应
        if request.stream:
            async def generate_stream():
                try:
                    async for chunk in provider.get_completion_stream(completion_request):
                        import json
                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                    yield "data: [DONE]\n\n"
                except ValueError as e:
                    # LiteLLM 友好错误（如 API Key 无效、速率限制等）
                    logger.error(f"流式补全错误: {e}")
                    import json
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                except Exception as e:
                    logger.error(f"流式补全异常: {e}", exc_info=True)
                    import json
                    yield f"data: {json.dumps({'error': f'补全失败: {str(e)}'})}\n\n"
            
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream"
            )
        
        # 非流式响应
        else:
            response = await provider.get_completion(completion_request)
            
            return {
                "status": "success",
                "content": response.content,
                "model": response.model,
                "finish_reason": response.finish_reason,
                "usage": response.usage
            }
            
    except HTTPException:
        raise
    except ValueError as e:
        # LiteLLM 友好错误
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"聊天补全失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embeddings")
async def create_embeddings(request: EmbeddingRequest):
    """
    文本向量化端点（统一通过 LiteLLM）
    
    支持：
    - 单个文本或文本列表向量化
    - 云端模型（OpenAI, Cohere等）
    
    模型命名规范：
    - openai:text-embedding-3-small -> OpenAI 嵌入模型
    - openai:text-embedding-3-large -> OpenAI 大型嵌入模型
    - cohere:embed-english-v3.0 -> Cohere 嵌入模型
    """
    try:
        ai_provider = get_ai_provider()
        response, used_model = await ai_provider.get_embedding(request.input, model=request.model)
        
        # 格式化响应
        embeddings = []
        for item in response.data:
            embeddings.append({
                "index": item["index"],
                "embedding": item["embedding"],
                "object": "embedding"
            })
        
        return {
            "status": "success",
            "object": "list",
            "data": embeddings,
            "model": used_model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # LiteLLM 友好错误
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"向量化失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
