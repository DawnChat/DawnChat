import os
import time

from app.api.cloud_models_routes import initialize_providers
from app.plugins import get_plugin_manager
from app.services.llama_binary_manager import get_binary_manager
from app.services.model_lifecycle_manager import get_lifecycle_manager
from app.services.network_service import NetworkService
from app.services.playwright_installer import PlaywrightInstaller
from app.storage import storage_manager
from app.utils.logger import app_logger as logger
from app.voice.azure_tts_service import get_azure_tts_service


async def initialize_non_critical_components(startup_start: float) -> None:
    """Initialize non-blocking subsystems in background."""
    try:
        import stat
        import sys
        import zipfile

        base_path = sys.__dict__.get("_MEIPASS")
        if not base_path:
            base_path = os.path.abspath(".")

        browser_root = os.path.join(base_path, "playwright", "driver", "package", ".local-browsers")
        chromium_dir = os.path.join(browser_root, "chromium-1194")
        zip_path = os.path.join(browser_root, "chromium-1194.zip")

        if os.path.exists(zip_path) and not os.path.exists(chromium_dir):
            logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 📦 解压 Playwright 浏览器...")
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(browser_root)

                logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 🔐 恢复浏览器执行权限...")
                for root, _dirs, files in os.walk(chromium_dir):
                    for name in files:
                        file_path = os.path.join(root, name)
                        try:
                            st = os.stat(file_path)
                            os.chmod(file_path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                        except Exception as e:
                            logger.warning(f"无法设置权限 {file_path}: {e}")

                logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ Playwright 浏览器准备就绪")
            except Exception as e:
                logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ Playwright 浏览器解压/配置失败: {e}")

        if not os.path.exists(chromium_dir):
            logger.warning(
                f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ⚠️ 未找到预打包浏览器，尝试在线下载 (Playwright install)..."
            )
            try:
                await PlaywrightInstaller.install_chromium(startup_start)
            except Exception as e:
                logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ Playwright 浏览器在线下载失败: {e}")
    except Exception as e:
        logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ Playwright 检查异常: {e}")

    try:
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 💾 存储管理器初始化...")
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ 存储管理器就绪")

        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 🌐 网络服务初始化...")
        await NetworkService.initialize()
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ 网络服务就绪")
    except Exception as e:
        logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ 存储管理器/网络服务初始化异常: {e}")

    try:
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ☁️  云端模型配置加载...")
        await initialize_providers()
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ 云端模型配置加载完成")
    except Exception as e:
        logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ 云端模型配置加载失败: {e}")

    try:
        binary_manager = get_binary_manager()
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 🧠 llama.cpp 二进制部署...")

        init_start = time.time()
        binary_path = await binary_manager.ensure_binary()
        init_duration = int((time.time() - init_start) * 1000)

        if binary_path:
            logger.info(
                f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ llama.cpp 二进制就绪 (耗时: {init_duration}ms)"
            )
        else:
            logger.warning(
                f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ⚠️ llama.cpp 二进制部署失败，本地 AI 功能可能不可用"
            )
    except Exception as e:
        logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ llama.cpp 二进制部署异常: {e}")

    try:
        logger.info(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] 📦 Plugin 管理器初始化...")
        plugin_manager = get_plugin_manager()
        await plugin_manager.initialize()
        plugins = plugin_manager.list_plugins()
        logger.info(
            f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ✅ Plugin 管理器初始化成功 (已注册插件: {len(plugins)})"
        )
    except Exception as e:
        logger.error(f"⏱️  [{int((time.time() - startup_start) * 1000)}ms] ❌ Plugin 管理器初始化异常: {e}")


async def shutdown_components() -> None:
    """Gracefully shutdown managed services."""
    try:
        lifecycle = get_lifecycle_manager()
        await lifecycle.shutdown()
        logger.info("✅ 模型生命周期管理器已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭模型生命周期管理器时发生异常: {e}", exc_info=True)

    try:
        from app.services.llama_server_manager import get_server_manager

        llama_manager = get_server_manager()
        await llama_manager.stop(force=True)
        logger.info("✅ llama-server 已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭 llama-server 时发生异常: {e}", exc_info=True)

    try:
        from app.services.mlx_server_manager import get_mlx_server_manager

        mlx_manager = get_mlx_server_manager()
        await mlx_manager.lm.stop(force=True)
        await mlx_manager.vlm.stop(force=True)
        logger.info("✅ MLX Server 已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭 MLX Server 时发生异常: {e}", exc_info=True)

    try:
        plugin_manager = get_plugin_manager()
        await plugin_manager.shutdown()
        logger.info("✅ Plugin 管理器已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭 Plugin 管理器时发生异常: {e}", exc_info=True)

    try:
        azure_tts_service = get_azure_tts_service()
        await azure_tts_service.aclose()
        logger.info("✅ Azure TTS HTTP 客户端已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭 Azure TTS HTTP 客户端时发生异常: {e}", exc_info=True)

    try:
        storage_manager.close()
        logger.info("✅ 存储管理器已关闭")
    except Exception as e:
        logger.error(f"❌ 关闭存储管理器时发生异常: {e}", exc_info=True)

