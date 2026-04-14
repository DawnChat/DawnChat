package com.dawnchat.app.auth

import android.net.Uri
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.util.UUID

internal object DesktopAuthBridgeConstants {
    const val PROTOCOL_VERSION = "1"
    /** Same as [@dawnchat/auth-bridge] DESKTOP_AUTH_CLIENT */
    const val CLIENT = "desktop"
    const val DEFAULT_BRIDGE_PATH = "/desktop-auth/bridge"
    const val PENDING_TTL_MS = 10 * 60 * 1000L
    const val DEFAULT_NEXT = "/app/workbench"
}

internal fun generateDesktopAuthState(): String =
    "dc_" + UUID.randomUUID().toString().replace("-", "")

internal fun normalizeNextPath(value: String?): String {
    val v = value?.trim().orEmpty()
    if (!v.startsWith("/") || v.startsWith("//")) return DesktopAuthBridgeConstants.DEFAULT_NEXT
    val safe = Regex("^/(app|fullscreen)(/|\$)")
    return if (safe.containsMatchIn(v)) v else DesktopAuthBridgeConstants.DEFAULT_NEXT
}

/**
 * Mirrors `@dawnchat/auth-bridge` `buildDesktopAuthBridgeUrl` (query param names and semantics).
 */
internal fun buildDesktopAuthBridgeUrl(
    baseUrl: String,
    state: String,
    deviceId: String,
    redirectUri: String,
    nextPath: String,
    provider: String?,
): String {
    val trimmed = baseUrl.trim()
    val http = trimmed.toHttpUrlOrNull() ?: throw IllegalArgumentException("Invalid bridge base URL")
    val withPath = if (http.encodedPath == "/" || http.encodedPath.isEmpty()) {
        http.newBuilder().encodedPath(DesktopAuthBridgeConstants.DEFAULT_BRIDGE_PATH).build()
    } else {
        http
    }
    val b = withPath.newBuilder()
    b.addQueryParameter("client", DesktopAuthBridgeConstants.CLIENT)
    b.addQueryParameter("state", state)
    b.addQueryParameter("device_id", deviceId)
    b.addQueryParameter("redirect_uri", redirectUri)
    b.addQueryParameter("next", normalizeNextPath(nextPath))
    b.addQueryParameter("protocol_version", DesktopAuthBridgeConstants.PROTOCOL_VERSION)
    when (provider) {
        "google", "github" -> b.addQueryParameter("provider", provider)
        else -> { }
    }
    return b.build().toString()
}

internal data class ParsedAuthCallback(
    val ticket: String?,
    val state: String?,
    val error: String?,
)

private fun parseQueryParams(rawQuery: String?): Map<String, String> {
    if (rawQuery.isNullOrBlank()) return emptyMap()
    return rawQuery.split('&').mapNotNull { segment ->
        if (segment.isEmpty()) return@mapNotNull null
        val eq = segment.indexOf('=')
        val key = URLDecoder.decode(if (eq >= 0) segment.take(eq) else segment, StandardCharsets.UTF_8)
        val value = URLDecoder.decode(if (eq >= 0) segment.drop(eq + 1) else "", StandardCharsets.UTF_8)
        key to value
    }.toMap()
}

/**
 * Custom schemes (`com.dawnchat.app://…`) are parsed with [URI]; HTTPS bridge URLs still use OkHttp elsewhere.
 */
internal fun parseDesktopAuthCallbackUrl(urlString: String): ParsedAuthCallback {
    return try {
        val uri = URI(urlString)
        val params = parseQueryParams(uri.rawQuery)
        ParsedAuthCallback(
            ticket = params["ticket"]?.takeIf { it.isNotEmpty() },
            state = params["state"]?.takeIf { it.isNotEmpty() },
            error = params["error_description"]?.takeIf { it.isNotEmpty() }
                ?: params["error"]?.takeIf { it.isNotEmpty() },
        )
    } catch (_: Exception) {
        ParsedAuthCallback(null, null, "invalid_callback_url")
    }
}

internal fun matchesAuthRedirectString(callbackUrl: String, expectedRedirect: String): Boolean {
    return try {
        val got = URI(callbackUrl)
        val exp = URI(expectedRedirect)
        got.scheme.equals(exp.scheme, ignoreCase = true) &&
            (got.host ?: "").equals(exp.host ?: "", ignoreCase = true) &&
            got.path.trimEnd('/') == exp.path.trimEnd('/')
    } catch (_: Exception) {
        false
    }
}

internal fun parseDesktopAuthCallback(uri: Uri): ParsedAuthCallback =
    parseDesktopAuthCallbackUrl(uri.toString())

internal fun isAuthCallbackUri(uri: Uri, expectedRedirect: String): Boolean =
    matchesAuthRedirectString(uri.toString(), expectedRedirect)
