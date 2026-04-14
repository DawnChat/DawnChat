package com.dawnchat.app.builtin

import android.content.Context
import android.util.Log
import com.dawnchat.app.data.plugin.PluginMetadata
import com.dawnchat.app.data.plugin.PluginStorageService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.InputStream

private const val TAG = "BuiltinPluginSeeder"

data class BundledManifest(
    val pluginId: String,
    val version: String,
    val name: String,
    val entry: String,
)

object BuiltinPluginSeeder {

    /** Version from packaged [builtin-manifest.json] (for auto-open gating). */
    fun embeddedCatalogVersion(context: Context): String {
        val app = context.applicationContext
        return readBundledManifest(app)?.version ?: BuiltinMobileAssistant.FALLBACK_BUNDLED_VERSION
    }

    /**
     * Ensures built-in web assets are copied into plugin storage and metadata is consistent.
     * Safe to call on every resume; skips copy when the entry file already exists.
     */
    suspend fun seedIfNeeded(context: Context) = withContext(Dispatchers.IO) {
        val app = context.applicationContext
        val manifest = readBundledManifest(app) ?: BundledManifest(
            pluginId = BuiltinMobileAssistant.PLUGIN_ID,
            version = BuiltinMobileAssistant.FALLBACK_BUNDLED_VERSION,
            name = BuiltinMobileAssistant.DISPLAY_NAME,
            entry = BuiltinMobileAssistant.ENTRY,
        )
        val storage = PluginStorageService(app)
        val versionDir = storage.getVersionDir(manifest.pluginId, manifest.version)
        val entryFile = File(versionDir, manifest.entry)

        if (!entryFile.isFile) {
            runCatching {
                copyRecursivelyFromAssets(
                    app,
                    "${BuiltinMobileAssistant.ASSET_ROOT}/${manifest.version}",
                    versionDir,
                )
            }.onFailure { e ->
                Log.w(TAG, "Built-in assistant assets missing or copy failed: ${e.message}")
                return@withContext
            }
        }

        if (!File(versionDir, manifest.entry).isFile) {
            Log.w(TAG, "Built-in assistant entry missing after seed: ${manifest.entry}")
            return@withContext
        }

        val existing = storage.readMetadata(manifest.pluginId)
        val prefs = HostBuiltinAssistantPrefs
        val lastLineage = prefs.lastLineageVersion(app)

        when {
            existing == null -> {
                storage.writeMetadata(
                    PluginMetadata(
                        pluginId = manifest.pluginId,
                        name = manifest.name,
                        currentVersion = manifest.version,
                        entry = manifest.entry,
                        updatedAt = System.currentTimeMillis(),
                        installStatus = PluginMetadata.STATUS_SUCCESS,
                    ),
                )
                prefs.setLastLineageVersion(app, manifest.version)
            }

            !prefs.isLineageExternal(app) &&
                lastLineage != null &&
                existing.pluginId == manifest.pluginId &&
                existing.currentVersion == lastLineage &&
                lastLineage != manifest.version -> {
                storage.writeMetadata(
                    PluginMetadata(
                        pluginId = manifest.pluginId,
                        name = manifest.name,
                        currentVersion = manifest.version,
                        entry = manifest.entry,
                        updatedAt = System.currentTimeMillis(),
                        installStatus = PluginMetadata.STATUS_SUCCESS,
                    ),
                )
                prefs.setLastLineageVersion(app, manifest.version)
            }

            existing.pluginId == manifest.pluginId && existing.currentVersion == manifest.version -> {
                storage.writeMetadata(
                    existing.copy(
                        name = manifest.name,
                        entry = manifest.entry,
                        updatedAt = System.currentTimeMillis(),
                    ),
                )
            }

            else -> Unit
        }
    }

    internal fun readBundledManifest(context: Context): BundledManifest? {
        return runCatching {
            context.assets.open("${BuiltinMobileAssistant.ASSET_ROOT}/builtin-manifest.json").use { input ->
                val o = JSONObject(input.bufferedReader().readText())
                BundledManifest(
                    pluginId = o.getString("pluginId"),
                    version = o.getString("version"),
                    name = o.getString("name"),
                    entry = o.optString("entry", BuiltinMobileAssistant.ENTRY),
                )
            }
        }.getOrNull()
    }

    private fun copyRecursivelyFromAssets(context: Context, assetPath: String, dest: File) {
        val am = context.assets
        val children = am.list(assetPath)
        when {
            children == null -> {
                am.open(assetPath).use { input -> input.copyToFile(dest) }
            }
            children.isEmpty() -> {
                dest.mkdirs()
            }
            else -> {
                dest.mkdirs()
                for (name in children) {
                    copyRecursivelyFromAssets(context, "$assetPath/$name", File(dest, name))
                }
            }
        }
    }

    private fun InputStream.copyToFile(file: File) {
        file.parentFile?.mkdirs()
        file.outputStream().use { out -> copyTo(out) }
    }
}
