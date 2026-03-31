"""
DawnChat - 后端主应用
FastAPI 应用入口，集成所有路由和中间件
"""

from contextlib import asynccontextmanager
import os
import platform

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from app.bootstrap.lifecycle import initialize_non_critical_components, shutdown_components
from app.bootstrap.routes import include_api_routers
from app.config import Config
from app.plugins import get_plugin_manager
from app.services.ffmpeg_manager import inject_ffmpeg_env
from app.services.parent_watcher import start_parent_watcher, stop_parent_watcher
from app.utils.logger import app_logger as logger

inject_ffmpeg_env()
# ============================================================================
# 禁用 hf_xet（Rust 加速库）
# 原因：hf_xet 使用 Rust 实现，其进度回调机制与 Python tqdm_class 不兼容
# 禁用后强制使用 HTTP 下载，确保 tqdm_class.update() 被正确调用
# ============================================================================
os.environ["HF_HUB_DISABLE_XET"] = "1"
# ============================================================

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理 - 优化启动速度"""
        import asyncio
        import time

        startup_start = time.time()
        logger.info(f"⏱️  [0ms] 🚀 DawnChat Backend v{Config.VERSION} 正在启动...")

        logger.info(f"🖥️  运行平台: {platform.system()} {platform.release()}")
        logger.info(f"📦 应用目录: {Config.PROJECT_ROOT}")
        logger.info(f"🧪 Test Mode: {Config.TEST_MODE}")
        if Config.TEST_MODE:
            logger.info("🧪 [Test Mode] E2E 测试模式已启用，将使用 ScenarioExecutor 替代真实执行器")

        total_duration = int((time.time() - startup_start) * 1000)
        logger.info(f"⏱️  [{total_duration}ms] ✅ DawnChat Backend 启动完成 (总耗时: {total_duration}ms)")
        logger.info("🌐 服务器已就绪，后台继续初始化非关键组件...")

        asyncio.create_task(initialize_non_critical_components(startup_start))

        parent_watcher_task = start_parent_watcher()
        if parent_watcher_task:
            logger.info("🔭 父进程监控已启动")

        yield

        logger.info("🛑 DawnChat Backend 正在关闭...")

        stop_parent_watcher()
        logger.info("✅ 父进程监控已停止")

        await shutdown_components()

        logger.info("👋 DawnChat Backend 已关闭")

    app = FastAPI(
        title="DawnChat API",
        version=Config.VERSION,
        description="DawnChat 后端 API - AI 驱动的信息策展平台",
        lifespan=lifespan,
    )

    plugin_manager = get_plugin_manager()
    plugin_manager.bind_app(app)

    app.state.api_host = Config.API_HOST
    app.state.api_port = Config.API_PORT

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        error_details = []
        for error in errors:
            loc = " -> ".join(str(loc_item) for loc_item in error.get("loc", []))
            msg = error.get("msg", "Unknown error")
            error_details.append(f"{loc}: {msg}")

        detail_str = "; ".join(error_details)
        logger.error(f"[Validation Error] {request.method} {request.url.path}: {detail_str}")

        return JSONResponse(
            status_code=422,
            content={
                "detail": errors,
                "message": detail_str,
                "path": str(request.url.path),
            },
        )

    include_api_routers(app)

    @app.get("/")
    def read_root():
        return {
            "name": Config.APP_NAME,
            "version": Config.VERSION,
            "message": "DawnChat Backend is running",
            "api_docs": "/docs",
        }

    return app


# 打包后需要显式启动 uvicorn 服务器
app = create_app()
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=app.state.api_host,
        port=app.state.api_port,
        log_level="info"
    )
