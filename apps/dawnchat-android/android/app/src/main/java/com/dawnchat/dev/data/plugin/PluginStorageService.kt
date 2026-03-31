package com.dawnchat.dev.data.plugin

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.util.Locale

class PluginStorageService(context: Context) {

    private val rootDir = File(context.filesDir, ROOT_PATH)

    init {
        if (!rootDir.exists()) {
            rootDir.mkdirs()
        }
    }

    data class PluginPaths(
        val pluginDir: File,
        val versionsDir: File,
        val tmpDir: File,
        val tmpZipFile: File,
        val tmpExtractDir: File,
        val metadataFile: File,
    )

    fun listPlugins(): List<PluginMetadata> {
        if (!rootDir.exists()) return emptyList()
        return rootDir.listFiles()
            ?.asSequence()
            ?.filter { it.isDirectory }
            ?.mapNotNull { readMetadata(it) }
            ?.filter { it.installStatus == PluginMetadata.STATUS_SUCCESS }
            ?.sortedByDescending { it.updatedAt }
            ?.toList()
            ?: emptyList()
    }

    fun buildPaths(pluginId: String, version: String): PluginPaths {
        val safePluginId = sanitizeSegment(pluginId)
        val safeVersion = sanitizeSegment(version)
        val pluginDir = File(rootDir, safePluginId)
        val versionsDir = File(pluginDir, "versions")
        val tmpDir = File(pluginDir, "tmp")
        val tmpZipFile = File(tmpDir, "bundle.zip")
        val tmpExtractDir = File(tmpDir, "extract")
        val metadataFile = File(pluginDir, "metadata.json")
        pluginDir.mkdirs()
        versionsDir.mkdirs()
        tmpDir.mkdirs()
        return PluginPaths(
            pluginDir = pluginDir,
            versionsDir = versionsDir,
            tmpDir = tmpDir,
            tmpZipFile = tmpZipFile,
            tmpExtractDir = tmpExtractDir,
            metadataFile = metadataFile,
        )
    }

    fun getVersionDir(pluginId: String, version: String): File {
        val paths = buildPaths(pluginId, version)
        return File(paths.versionsDir, sanitizeSegment(version))
    }

    fun writeMetadata(metadata: PluginMetadata) {
        val paths = buildPaths(metadata.pluginId, metadata.currentVersion)
        val json = JSONObject().apply {
            put("pluginId", metadata.pluginId)
            put("name", metadata.name)
            put("currentVersion", metadata.currentVersion)
            put("entry", metadata.entry)
            put("updatedAt", metadata.updatedAt)
            put("installStatus", metadata.installStatus)
        }
        paths.metadataFile.writeText(json.toString())
    }

    fun readMetadata(pluginId: String): PluginMetadata? {
        val pluginDir = File(rootDir, sanitizeSegment(pluginId))
        return readMetadata(pluginDir)
    }

    fun buildLocalHost(pluginId: String): String {
        val hostSafe = buildLocalHostToken(pluginId)
        return "https://$hostSafe.dawnchat.local"
    }

    fun buildLocalHostToken(pluginId: String): String {
        val normalized = pluginId
            .lowercase(Locale.US)
            .replace(Regex("[^a-z0-9-]"), "-")
            .replace(Regex("-+"), "-")
            .trim('-')
        val token = if (normalized.isBlank()) "plugin" else normalized
        return "plugin-$token"
    }

    private fun readMetadata(pluginDir: File): PluginMetadata? {
        val metadataFile = File(pluginDir, "metadata.json")
        if (!metadataFile.exists()) return null
        return runCatching {
            val json = JSONObject(metadataFile.readText())
            PluginMetadata(
                pluginId = json.getString("pluginId"),
                name = json.optString("name", json.getString("pluginId")),
                currentVersion = json.getString("currentVersion"),
                entry = json.optString("entry", "index.html"),
                updatedAt = json.optLong("updatedAt", 0L),
                installStatus = json.optString("installStatus", PluginMetadata.STATUS_SUCCESS),
            )
        }.getOrNull()
    }

    companion object {
        private const val ROOT_PATH = "DawnChatMobile/plugins"

        fun sanitizeSegment(value: String): String {
            return value.replace(Regex("[^A-Za-z0-9._-]"), "_")
        }
    }
}
