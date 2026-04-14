package com.dawnchat.app.plugins

import android.util.Log
import com.dawnchat.app.DawnChatApp
import com.dawnchat.app.R
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import io.github.jan.supabase.auth.auth
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * POST dawn-tts Edge function with Supabase session token; writes audio/mpeg to cache and returns absolute path.
 * Token never crosses into JS.
 */
@CapacitorPlugin(name = "DawnTts")
class DawnTtsPlugin : Plugin() {

    private val httpClient: OkHttpClient =
        OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

    @PluginMethod
    fun synthesizeToFile(call: PluginCall) {
        val text = call.getString("text")?.trim().orEmpty()
        if (text.isEmpty()) {
            call.reject("Field text is required", "text_required")
            return
        }

        val voice = call.getString("voice")?.trim()
        val rate = call.getString("rate")?.trim()
        val volume = call.getString("volume")?.trim()
        val pitch = call.getString("pitch")?.trim()

        val app = activity.applicationContext as? DawnChatApp
        val client = app?.supabaseClientOrNull()
        val session = client?.auth?.currentSessionOrNull()
        val accessToken = session?.accessToken?.trim().orEmpty()
        if (accessToken.isEmpty()) {
            call.reject("Not signed in or session has no access token", "not_authenticated")
            return
        }

        val baseUrl = activity.getString(R.string.dawnchat_supabase_url).trim().trimEnd('/')
        val anonKey = activity.getString(R.string.dawnchat_supabase_anon_key).trim()
        if (baseUrl.isEmpty() || anonKey.isEmpty()) {
            call.reject("Supabase URL or anon key is not configured", "supabase_config_missing")
            return
        }

        val url = "$baseUrl/functions/v1/dawn-tts"
        val bodyJson = JSONObject()
        bodyJson.put("text", text)
        if (!voice.isNullOrEmpty()) bodyJson.put("voice", voice)
        if (!rate.isNullOrEmpty()) bodyJson.put("rate", rate)
        if (!volume.isNullOrEmpty()) bodyJson.put("volume", volume)
        if (!pitch.isNullOrEmpty()) bodyJson.put("pitch", pitch)

        val mediaType = JSON_MEDIA
        val requestBody = bodyJson.toString().toRequestBody(mediaType)
        val request =
            Request.Builder()
                .url(url)
                .post(requestBody)
                .header("Authorization", "Bearer $accessToken")
                .header("apikey", anonKey)
                .header("Content-Type", "application/json")
                .header("Accept", "audio/mpeg")
                .build()

        Thread {
            try {
                httpClient.newCall(request).execute().use { response ->
                    val bytes = response.body.bytes()
                    if (!response.isSuccessful) {
                        val parsed = parseErrorJson(bytes)
                        val code = parsed.first ?: "dawn_tts_http_${response.code}"
                        val message = parsed.second ?: response.message.ifEmpty { "HTTP ${response.code}" }
                        activity.runOnUiThread { call.reject(message, code) }
                        return@use
                    }

                    val contentType = response.header("Content-Type")?.lowercase().orEmpty()
                    if (contentType.contains("application/json")) {
                        activity.runOnUiThread {
                            call.reject("Unexpected JSON response; ensure Accept is audio/mpeg", "unexpected_json")
                        }
                        return@use
                    }

                    val dir = File(activity.cacheDir, "dawn-tts").apply { mkdirs() }
                    val outFile = File(dir, "${UUID.randomUUID()}.mp3")
                    outFile.writeBytes(bytes)

                    val ret = JSObject()
                    ret.put("path", outFile.absolutePath)
                    activity.runOnUiThread { call.resolve(ret) }
                }
            } catch (e: Exception) {
                Log.e(TAG, "synthesizeToFile failed", e)
                activity.runOnUiThread {
                    call.reject(e.message ?: "request failed", "dawn_tts_request_failed", e)
                }
            }
        }.start()
    }

    private fun parseErrorJson(bytes: ByteArray): Pair<String?, String?> {
        if (bytes.isEmpty()) return null to null
        return try {
            val jo = JSONObject(bytes.decodeToString())
            val code = jo.optString("code", "").trim().takeIf { it.isNotEmpty() }
            val message = jo.optString("message", "").trim().takeIf { it.isNotEmpty() }
            code to message
        } catch (_: Exception) {
            null to null
        }
    }

    companion object {
        private const val TAG = "DawnTtsPlugin"
        private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()
    }
}
