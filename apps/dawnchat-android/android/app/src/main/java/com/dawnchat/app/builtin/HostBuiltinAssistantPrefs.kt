package com.dawnchat.app.builtin

import android.content.Context

/**
 * Tracks built-in assistant lineage vs user-installed versions from QR (see [BuiltinPluginSeeder]).
 */
object HostBuiltinAssistantPrefs {

    private const val PREFS_BUILTIN = "host_builtin_assistant"
    private const val KEY_LAST_LINEAGE = "last_lineage_version"
    const val KEY_AUTO_OPENED_EMBEDDED_VERSION = "auto_opened_embedded_version"

    private const val PREFS_HOST = "host_settings"
    const val KEY_AUTO_OPEN_ENABLED = "auto_open_mobile_assistant"

    internal const val EXTERNAL_LINEAGE = "__external__"

    private fun builtinPrefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS_BUILTIN, Context.MODE_PRIVATE)

    fun lastLineageVersion(context: Context): String? =
        builtinPrefs(context).getString(KEY_LAST_LINEAGE, null)

    fun setLastLineageVersion(context: Context, version: String) {
        builtinPrefs(context).edit().putString(KEY_LAST_LINEAGE, version).apply()
    }

    /** Call after a QR/bundle install for the official assistant id so we do not overwrite user-picked versions. */
    fun markExternalInstall(context: Context, pluginId: String) {
        if (pluginId == BuiltinMobileAssistant.PLUGIN_ID) {
            builtinPrefs(context).edit().putString(KEY_LAST_LINEAGE, EXTERNAL_LINEAGE).apply()
        }
    }

    fun isLineageExternal(context: Context): Boolean =
        EXTERNAL_LINEAGE == lastLineageVersion(context)

    fun isAutoOpenEnabled(context: Context): Boolean =
        context.applicationContext.getSharedPreferences(PREFS_HOST, Context.MODE_PRIVATE)
            .getBoolean(KEY_AUTO_OPEN_ENABLED, true)

    fun autoOpenedEmbeddedVersion(context: Context): String? =
        builtinPrefs(context).getString(KEY_AUTO_OPENED_EMBEDDED_VERSION, null)

    fun setAutoOpenedEmbeddedVersion(context: Context, version: String) {
        builtinPrefs(context).edit().putString(KEY_AUTO_OPENED_EMBEDDED_VERSION, version).apply()
    }
}
