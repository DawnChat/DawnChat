package com.dawnchat.app.auth

import io.github.jan.supabase.auth.user.UserSession

/**
 * Builds a [UserSession] for [io.github.jan.supabase.auth.Auth.importSession] from Edge Function tokens.
 */
fun userSessionFromExchangeTokens(tokens: DesktopTicketExchangeTokens): UserSession {
    val expiresIn = expiresInSeconds(tokens.expiresAt)
    return UserSession(
        accessToken = tokens.accessToken,
        refreshToken = tokens.refreshToken,
        expiresIn = expiresIn,
        tokenType = "Bearer",
        user = null,
    )
}

/** Seconds until access token expiry; conservative default when unknown. */
private fun expiresInSeconds(expiresAt: Long?): Long {
    val fallback = 3600L
    if (expiresAt == null) return fallback
    val nowSec = System.currentTimeMillis() / 1000
    val expSec = if (expiresAt > 1_000_000_000_000L) expiresAt / 1000 else expiresAt
    return maxOf(60L, expSec - nowSec)
}
