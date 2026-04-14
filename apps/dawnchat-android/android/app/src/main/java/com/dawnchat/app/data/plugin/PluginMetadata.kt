package com.dawnchat.app.data.plugin

data class PluginMetadata(
    val pluginId: String,
    val name: String,
    val currentVersion: String,
    val entry: String,
    val updatedAt: Long,
    val installStatus: String = STATUS_SUCCESS,
) {
    companion object {
        const val STATUS_SUCCESS = "success"
        const val STATUS_FAILED = "failed"
    }
}
