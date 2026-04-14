package com.dawnchat.app.builtin

/**
 * Defaults when [builtin-manifest.json] is missing or incomplete.
 * After running [scripts/mobile/build-builtin-mobile-assistant.sh], manifest on disk is authoritative for version.
 */
object BuiltinMobileAssistant {
    const val PLUGIN_ID: String = "com.dawnchat.mobile-ai-assistant"
    const val DISPLAY_NAME: String = "Mobile AI Assistant"
    const val ENTRY: String = "index.html"
    const val ASSET_ROOT: String = "builtin_mobile_assistant"
    const val FALLBACK_BUNDLED_VERSION: String = "1.0.0"
}
