package com.dawnchat.app.auth

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.regex.Pattern

data class DesktopTicketExchangeTokens(
    val accessToken: String,
    val refreshToken: String,
    val expiresAt: Long?,
)

private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

/** RFC 8259 string literal for JSON object values (ticket/state/deviceId are bounded by Edge Function). */
internal fun jsonStringLiteral(value: String): String {
    val sb = StringBuilder(value.length + 16)
    sb.append('"')
    for (c in value) {
        when (c) {
            '\\' -> sb.append("\\\\")
            '"' -> sb.append("\\\"")
            '\n' -> sb.append("\\n")
            '\r' -> sb.append("\\r")
            '\t' -> sb.append("\\t")
            else -> if (c.code < 0x20) {
                sb.append("\\u%04x".format(c.code))
            } else {
                sb.append(c)
            }
        }
    }
    sb.append('"')
    return sb.toString()
}

internal fun buildExchangeRequestBody(ticket: String, state: String, deviceId: String): String =
    """{"desktop_ticket":${jsonStringLiteral(ticket)},"state":${jsonStringLiteral(state)},"device_id":${jsonStringLiteral(deviceId)},"protocol_version":"${DesktopAuthBridgeConstants.PROTOCOL_VERSION}"}"""

private val ACCESS_TOKEN_PATTERN = Pattern.compile(
    "\"access_token\"\\s*:\\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"",
)
private val REFRESH_TOKEN_PATTERN = Pattern.compile(
    "\"refresh_token\"\\s*:\\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"",
)
private val EXPIRES_AT_PATTERN = Pattern.compile("\"expires_at\"\\s*:\\s*([0-9]+)")
private val MESSAGE_PATTERN = Pattern.compile(
    "\"message\"\\s*:\\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"",
)
private val CODE_PATTERN = Pattern.compile("\"code\"\\s*:\\s*\"([^\"\\\\]*(?:\\\\.[^\"\\\\]*)*)\"")

private fun unescapeJsonString(s: String): String =
    s.replace("\\\\", "\u0000")
        .replace("\\\"", "\"")
        .replace("\u0000", "\\")

internal fun parseExchangeSuccessResponse(text: String): Result<DesktopTicketExchangeTokens> {
    val accessM = ACCESS_TOKEN_PATTERN.matcher(text)
    val refreshM = REFRESH_TOKEN_PATTERN.matcher(text)
    if (!accessM.find() || !refreshM.find()) {
        return Result.failure(Exception("ticket 兑换结果缺少会话 token"))
    }
    val access = accessM.group(1)!!.trim()
    val refresh = refreshM.group(1)!!.trim()
    if (access.isEmpty() || refresh.isEmpty()) {
        return Result.failure(Exception("ticket 兑换结果缺少会话 token"))
    }
    val expM = EXPIRES_AT_PATTERN.matcher(text)
    val exp = if (expM.find()) expM.group(1)!!.toLongOrNull() else null
    return Result.success(DesktopTicketExchangeTokens(access, refresh, exp))
}

internal fun parseExchangeErrorMessage(text: String, code: Int): String {
    val msgM = MESSAGE_PATTERN.matcher(text)
    if (msgM.find()) {
        val raw = msgM.group(1)!!.trim()
        if (raw.isNotEmpty()) return raw
    }
    val codeM = CODE_PATTERN.matcher(text)
    if (codeM.find()) {
        val raw = codeM.group(1)!!.trim()
        if (raw.isNotEmpty()) return raw
    }
    return text.trim().ifEmpty { "ticket 兑换失败($code)" }
}

/**
 * POST `exchange-desktop-ticket` (same contract as desktop [useDesktopWebAuth]).
 * Avoids `org.json.JSONObject` so JVM unit tests are not blocked by Android SDK stubs.
 */
internal fun exchangeDesktopTicket(
    httpClient: OkHttpClient,
    supabaseUrl: String,
    anonKey: String,
    ticket: String,
    state: String,
    deviceId: String,
): Result<DesktopTicketExchangeTokens> {
    val base = supabaseUrl.trimEnd('/')
    val url = "$base/functions/v1/exchange-desktop-ticket"
    val body = buildExchangeRequestBody(ticket, state, deviceId)
    val req = Request.Builder()
        .url(url)
        .post(body.toRequestBody(JSON_MEDIA))
        .header("Content-Type", "application/json")
        .header("apikey", anonKey)
        .build()
    return try {
        httpClient.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) {
                return Result.failure(Exception(parseExchangeErrorMessage(text, resp.code)))
            }
            parseExchangeSuccessResponse(text)
        }
    } catch (e: Exception) {
        Result.failure(e)
    }
}
