package com.dawnchat.app.domain.plugin

import android.webkit.URLUtil
import org.json.JSONObject

class PluginPayloadParser {

    fun parse(rawText: String): Result<ScanPayload> = runCatching {
        val raw = rawText.trim()
        if (URLUtil.isHttpUrl(raw) || URLUtil.isHttpsUrl(raw)) {
            return@runCatching ScanPayload.Hmr(raw)
        }

        val json = JSONObject(raw)
        val schema = json.optString("schema")
        val type = json.optString("type")
        require(schema == SCHEMA_V1) { "Unsupported schema: $schema" }
        require(type == TYPE_BUNDLE) { "Unsupported type: $type" }

        val plugin = json.getJSONObject("plugin")
        val artifact = json.getJSONObject("artifact")

        ScanPayload.Bundle(
            BundlePayload(
                schema = schema,
                type = type,
                plugin = PluginInfo(
                    id = plugin.getString("id"),
                    name = plugin.optString("name", plugin.getString("id")),
                    version = plugin.getString("version"),
                    entry = plugin.optString("entry", "index.html"),
                ),
                artifact = ArtifactInfo(
                    url = artifact.getString("url"),
                    sha256 = artifact.getString("sha256"),
                    size = artifact.optLong("size"),
                    expiresAt = artifact.optString("expiresAt"),
                ),
                issuedAt = json.optString("issuedAt"),
            )
        )
    }

    companion object {
        const val SCHEMA_V1 = "dawnchat.mobile.plugin.v1"
        private const val TYPE_BUNDLE = "bundle"
    }
}

sealed class ScanPayload {
    data class Hmr(val url: String) : ScanPayload()
    data class Bundle(val payload: BundlePayload) : ScanPayload()
}

data class BundlePayload(
    val schema: String,
    val type: String,
    val plugin: PluginInfo,
    val artifact: ArtifactInfo,
    val issuedAt: String?,
)

data class PluginInfo(
    val id: String,
    val name: String,
    val version: String,
    val entry: String,
)

data class ArtifactInfo(
    val url: String,
    val sha256: String,
    val size: Long,
    val expiresAt: String?,
)
