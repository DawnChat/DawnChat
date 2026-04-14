package com.dawnchat.app

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.dawnchat.app.auth.DesktopTicketExchangeTokens
import com.dawnchat.app.auth.MobileAuthRepository
import com.dawnchat.app.auth.userSessionFromExchangeTokens
import io.github.jan.supabase.SupabaseClient
import io.github.jan.supabase.auth.Auth
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.createSupabaseClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class DawnChatApp : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    private var _supabase: SupabaseClient? = null

    fun supabaseClientOrNull(): SupabaseClient? = _supabase

    override fun onCreate() {
        super.onCreate()
        val url = getString(R.string.dawnchat_supabase_url).trim()
        val key = getString(R.string.dawnchat_supabase_anon_key).trim()
        if (url.isNotBlank() && key.isNotBlank()) {
            _supabase = createSupabaseClient(supabaseUrl = url, supabaseKey = key) {
                install(Auth)
            }
            appScope.launch { migrateLegacyTokensIfNeeded() }
        }
    }

    /**
     * One-shot: older builds stored tokens only in EncryptedSharedPreferences.
     * Import into Supabase Auth storage then strip legacy keys to avoid dual sources.
     */
    private suspend fun migrateLegacyTokensIfNeeded() {
        val client = _supabase ?: return
        val prefs = legacyAuthPrefs(this)
        val access = prefs.getString(MobileAuthRepository.LEGACY_KEY_ACCESS, null)
        val refresh = prefs.getString(MobileAuthRepository.LEGACY_KEY_REFRESH, null)
        if (access.isNullOrBlank() || refresh.isNullOrBlank()) return
        if (client.auth.currentSessionOrNull() != null) {
            clearLegacyTokenKeys(prefs)
            return
        }
        val expiresAt = prefs.getLong(MobileAuthRepository.LEGACY_KEY_EXPIRES_AT, 0L).takeIf { it > 0 }
        val tokens = DesktopTicketExchangeTokens(
            accessToken = access,
            refreshToken = refresh,
            expiresAt = expiresAt,
        )
        try {
            client.auth.importSession(userSessionFromExchangeTokens(tokens))
        } catch (_: Exception) {
            return
        }
        clearLegacyTokenKeys(prefs)
    }

    private fun clearLegacyTokenKeys(prefs: SharedPreferences) {
        prefs.edit()
            .remove(MobileAuthRepository.LEGACY_KEY_ACCESS)
            .remove(MobileAuthRepository.LEGACY_KEY_REFRESH)
            .remove(MobileAuthRepository.LEGACY_KEY_EXPIRES_AT)
            .apply()
    }

    private fun legacyAuthPrefs(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            MobileAuthRepository.PREFS_FILE,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }
}
