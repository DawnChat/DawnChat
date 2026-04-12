from fastapi import FastAPI


def include_api_routers(app: FastAPI) -> None:
    """Register all API routers in a single place."""
    from app.api import sdk_routes
    from app.api.agentv3_routes import router as agentv3_router
    from app.api.claude_routes import router as claude_router
    from app.api.cloud_models_routes import router as cloud_models_router
    from app.api.huggingface_routes import router as huggingface_router
    from app.api.local_ai_routes import router as local_ai_router
    from app.api.mobile_publish_routes import router as mobile_publish_router
    from app.api.network_routes import router as network_router
    from app.api.opencode_iwp_mcp_routes import router as opencode_iwp_mcp_router
    from app.api.opencode_mcp_routes import router as opencode_mcp_router
    from app.api.opencode_plugin_mcp_routes import router as opencode_plugin_mcp_router
    from app.api.opencode_plugin_python_mcp_routes import router as opencode_plugin_python_mcp_router
    from app.api.opencode_routes import router as opencode_router
    from app.api.opencode_search_mcp_routes import router as opencode_search_mcp_router
    from app.api.opencode_voice_mcp_routes import router as opencode_voice_mcp_router
    from app.api.plugin_ui_bridge_routes import router as plugin_ui_bridge_router
    from app.api.plugins_routes import router as plugins_router
    from app.api.routes import router
    from app.api.scoring_routes import router as scoring_router
    from app.api.storage_routes import router as storage_router
    from app.api.supabase_session_routes import router as supabase_session_router
    from app.api.tts_routes import router as tts_router
    from app.api.web_publish_routes import router as web_publish_router
    from app.api.workbench_projects_routes import router as workbench_projects_router

    app.include_router(router, prefix="/api")
    app.include_router(storage_router, prefix="/api")
    app.include_router(cloud_models_router, prefix="/api")
    app.include_router(local_ai_router, prefix="/api")
    app.include_router(huggingface_router, prefix="/api")
    app.include_router(agentv3_router, prefix="/api")
    app.include_router(network_router, prefix="/api")
    app.include_router(plugins_router, prefix="/api")
    app.include_router(workbench_projects_router, prefix="/api")
    app.include_router(opencode_router, prefix="/api")
    app.include_router(claude_router, prefix="/api")
    app.include_router(opencode_mcp_router, prefix="/api")
    app.include_router(opencode_plugin_mcp_router, prefix="/api")
    app.include_router(opencode_plugin_python_mcp_router, prefix="/api")
    app.include_router(opencode_iwp_mcp_router, prefix="/api")
    app.include_router(opencode_search_mcp_router, prefix="/api")
    app.include_router(opencode_voice_mcp_router, prefix="/api")
    app.include_router(scoring_router, prefix="/api")
    app.include_router(web_publish_router, prefix="/api")
    app.include_router(mobile_publish_router, prefix="/api")
    app.include_router(supabase_session_router, prefix="/api")
    app.include_router(tts_router, prefix="/api")
    app.include_router(plugin_ui_bridge_router)
    app.include_router(sdk_routes.router)
