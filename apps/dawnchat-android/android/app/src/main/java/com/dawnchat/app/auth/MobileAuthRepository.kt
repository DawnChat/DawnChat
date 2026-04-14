package com.dawnchat.app.auth

import android.content.Context
import android.net.Uri
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dawnchat.app.DawnChatApp
import com.dawnchat.app.R
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.auth.status.SessionStatus
import io.github.jan.supabase.auth.user.UserInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.TimeUnit

data class PendingAuthState(
    val state: String,
    val deviceId: String,
    val createdAt: Long,
    val nextPath: String?,
)

/** UI-facing snapshot from Supabase Auth [UserInfo]; avoids binding views to SDK types. */
data class UserProfileSnapshot(
    val id: String,
    val email: String?,
    val phone: String?,
    val displayName: String?,
    val avatarUrl: String?,
    val createdAtIso: String?,
    val lastSignInAtIso: String?,
)

private fun JsonObject?.metadataString(vararg keys: String): String? {
    if (this == null) return null
    for (key in keys) {
        val prim = get(key) as? JsonPrimitive ?: continue
        val s = prim.contentOrNull?.trim()?.takeIf { it.isNotEmpty() } ?: continue
        return s
    }
    return null
}

private fun UserInfo.toProfileSnapshot(): UserProfileSnapshot {
    val meta = userMetadata
    val display = meta.metadataString("full_name", "name", "display_name", "nickname")
    val avatar = meta.metadataString("avatar_url", "picture", "avatar")
    return UserProfileSnapshot(
        id = id,
        email = email?.trim()?.takeIf { it.isNotEmpty() },
        phone = phone?.trim()?.takeIf { it.isNotEmpty() },
        displayName = display,
        avatarUrl = avatar,
        createdAtIso = createdAt?.toString(),
        lastSignInAtIso = lastSignInAt?.toString(),
    )
}

class MobileAuthRepository(private val context: Context) {

    private val prefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun redirectUri(): String =
        context.getString(R.string.dawnchat_mobile_auth_redirect_uri).trim()

    fun bridgeBaseUrl(): String =
        context.getString(R.string.dawnchat_auth_bridge_base_url).trim()

    fun supabaseUrl(): String =
        context.getString(R.string.dawnchat_supabase_url).trim()

    fun supabaseAnonKey(): String =
        context.getString(R.string.dawnchat_supabase_anon_key).trim()

    fun isConfigReady(): Boolean =
        supabaseUrl().isNotBlank() && supabaseAnonKey().isNotBlank()

    fun matchesAuthRedirect(uri: Uri): Boolean =
        isAuthCallbackUri(uri, redirectUri())

    fun getOrCreateDeviceId(): String {
        val existing = prefs.getString(KEY_DEVICE_ID, null)
        if (!existing.isNullOrBlank()) return existing
        val id = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    /**
     * Best-effort sync check (after storage load). Prefer [awaitSessionVerifiedForLaunch] on cold start.
     */
    fun isLoggedIn(): Boolean {
        val app = context.applicationContext as? DawnChatApp ?: return false
        val client = app.supabaseClientOrNull() ?: return false
        return client.auth.currentSessionOrNull() != null
    }

    suspend fun clearSession() = withContext(Dispatchers.IO) {
        val app = context.applicationContext as? DawnChatApp
        try {
            app?.supabaseClientOrNull()?.auth?.signOut()
        } catch (_: Exception) {
        }
        clearLegacyTokenKeys()
    }

    /**
     * Maps current Supabase Auth user to a stable snapshot for Mine / profile screens.
     * Uses in-memory session first; if session exists but user is missing, calls [retrieveUserForCurrentSession] once.
     */
    suspend fun loadProfileForUi(): UserProfileSnapshot? = withContext(Dispatchers.IO) {
        val app = context.applicationContext as? DawnChatApp ?: return@withContext null
        val client = app.supabaseClientOrNull() ?: return@withContext null
        val auth = client.auth
        var user: UserInfo? = auth.currentSessionOrNull()?.user
        if (user == null && auth.currentSessionOrNull() != null) {
            user = try {
                auth.retrieveUserForCurrentSession(updateSession = false)
            } catch (_: Exception) {
                null
            }
        }
        user?.toProfileSnapshot()
    }

    /**
     * Waits for Auth to leave [SessionStatus.Initializing], then validates session when network is available.
     * When offline, trusts the SDK-restored session if status is [SessionStatus.Authenticated].
     *
     * Manual QA: cold start with valid session; airplane mode + Authenticated; refresh failure → login;
     * Release build with `minifyEnabled true` if enabled later (see proguard-rules.pro).
     */
    suspend fun awaitSessionVerifiedForLaunch(): Boolean = withContext(Dispatchers.IO) {
        val app = context.applicationContext as? DawnChatApp ?: return@withContext false
        val client = app.supabaseClientOrNull() ?: return@withContext false
        if (!isConfigReady()) return@withContext false

        val status = client.auth.sessionStatus.first { it !is SessionStatus.Initializing }
        when (status) {
            is SessionStatus.Authenticated -> {
                if (!context.hasInternetCapability()) {
                    return@withContext true
                }
                try {
                    client.auth.retrieveUserForCurrentSession(updateSession = true)
                    true
                } catch (_: Exception) {
                    try {
                        client.auth.signOut()
                    } catch (_: Exception) {
                    }
                    clearLegacyTokenKeys()
                    false
                }
            }
            is SessionStatus.NotAuthenticated,
            is SessionStatus.RefreshFailure,
            -> false
            else -> false
        }
    }

    private fun clearLegacyTokenKeys() {
        prefs.edit()
            .remove(LEGACY_KEY_ACCESS)
            .remove(LEGACY_KEY_REFRESH)
            .remove(LEGACY_KEY_EXPIRES_AT)
            .apply()
    }

    fun writePending(pending: PendingAuthState) {
        val o = JSONObject()
        o.put("state", pending.state)
        o.put("deviceId", pending.deviceId)
        o.put("createdAt", pending.createdAt)
        if (pending.nextPath != null) o.put("nextPath", pending.nextPath)
        prefs.edit().putString(KEY_PENDING, o.toString()).apply()
    }

    fun readPending(): PendingAuthState? {
        val raw = prefs.getString(KEY_PENDING, null) ?: return null
        return try {
            val o = JSONObject(raw)
            val nextPath = if (o.has("nextPath")) o.optString("nextPath", "") else ""
            PendingAuthState(
                state = o.getString("state"),
                deviceId = o.getString("deviceId"),
                createdAt = o.getLong("createdAt"),
                nextPath = nextPath.takeIf { it.isNotEmpty() },
            )
        } catch (_: Exception) {
            clearPending()
            null
        }
    }

    fun clearPending() {
        prefs.edit().remove(KEY_PENDING).apply()
    }

    fun pendingValid(): PendingAuthState? {
        val p = readPending() ?: return null
        if (System.currentTimeMillis() - p.createdAt > DesktopAuthBridgeConstants.PENDING_TTL_MS) {
            clearPending()
            return null
        }
        return p
    }

    fun prepareBridgeLogin(nextPath: String = DesktopAuthBridgeConstants.DEFAULT_NEXT): String {
        val state = generateDesktopAuthState()
        val deviceId = getOrCreateDeviceId()
        writePending(
            PendingAuthState(
                state = state,
                deviceId = deviceId,
                createdAt = System.currentTimeMillis(),
                nextPath = nextPath,
            ),
        )
        return buildDesktopAuthBridgeUrl(
            baseUrl = bridgeBaseUrl(),
            state = state,
            deviceId = deviceId,
            redirectUri = redirectUri(),
            nextPath = nextPath,
            provider = null,
        )
    }

    suspend fun completeAuthFromCallback(uri: Uri): Result<Unit> = withContext(Dispatchers.IO) {
        if (!matchesAuthRedirect(uri)) {
            return@withContext Result.failure(IllegalArgumentException("not_auth_callback"))
        }
        val parsed = parseDesktopAuthCallback(uri)
        if (!parsed.error.isNullOrBlank()) {
            clearPending()
            return@withContext Result.failure(Exception(parsed.error))
        }
        val ticket = parsed.ticket?.trim().orEmpty()
        val state = parsed.state?.trim().orEmpty()
        if (ticket.isEmpty() || state.isEmpty()) {
            return@withContext Result.failure(Exception("登录回调缺少 ticket 或 state"))
        }
        exchangeTicket(ticket, state)
    }

    private suspend fun exchangeTicket(ticket: String, state: String): Result<Unit> {
        val pending = pendingValid()
            ?: return Result.failure(IllegalStateException("登录状态已失效，请重新发起登录"))
        if (pending.state != state) {
            clearPending()
            return Result.failure(IllegalStateException("登录状态校验失败，请重新登录"))
        }
        if (!isConfigReady()) {
            return Result.failure(IllegalStateException("请在 auth_config.xml 或 debug 覆盖中配置 Supabase URL 与 anon key"))
        }
        val app = context.applicationContext as? DawnChatApp
        val client = app?.supabaseClientOrNull()
            ?: return Result.failure(IllegalStateException("Supabase 客户端未初始化"))
        val exchanged = exchangeDesktopTicket(
            httpClient,
            supabaseUrl(),
            supabaseAnonKey(),
            ticket,
            state,
            pending.deviceId,
        )
        val tokens = exchanged.getOrElse { return Result.failure(it) }
        return try {
            client.auth.importSession(userSessionFromExchangeTokens(tokens))
            clearPending()
            clearLegacyTokenKeys()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    companion object {
        const val PREFS_FILE = "dawnchat_mobile_auth"
        const val LEGACY_KEY_ACCESS = "supabase_access_token"
        const val LEGACY_KEY_REFRESH = "supabase_refresh_token"
        const val LEGACY_KEY_EXPIRES_AT = "supabase_expires_at"
        private const val KEY_DEVICE_ID = "device_install_id"
        private const val KEY_PENDING = "auth_pending_json"
    }
}
