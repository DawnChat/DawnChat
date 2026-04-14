package com.dawnchat.app.auth

import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pure JVM: matches [@dawnchat/auth-bridge] and avoids Robolectric (fast CI).
 */
class DesktopAuthBridgeTest {

    @Test
    fun buildBridgeUrl_matchesAuthBridgePackageShape() {
        val url = buildDesktopAuthBridgeUrl(
            baseUrl = "https://dawnchat.com",
            state = "dc_teststate",
            deviceId = "device-uuid",
            redirectUri = "com.dawnchat.app://auth/callback",
            nextPath = "/app/workbench",
            provider = null,
        )
        val http = url.toHttpUrl()
        assertEquals("https", http.scheme)
        assertEquals("dawnchat.com", http.host)
        assertEquals("/desktop-auth/bridge", http.encodedPath)
        assertEquals("desktop", http.queryParameter("client"))
        assertEquals("dc_teststate", http.queryParameter("state"))
        assertEquals("device-uuid", http.queryParameter("device_id"))
        assertEquals("com.dawnchat.app://auth/callback", http.queryParameter("redirect_uri"))
        assertEquals("/app/workbench", http.queryParameter("next"))
        assertEquals("1", http.queryParameter("protocol_version"))
    }

    @Test
    fun matchesAuthRedirectString_productionCallback() {
        assertTrue(
            matchesAuthRedirectString(
                "com.dawnchat.app://auth/callback?ticket=abc&state=dc_x",
                "com.dawnchat.app://auth/callback",
            ),
        )
    }

    @Test
    fun matchesAuthRedirectString_rejectsWrongHost() {
        assertFalse(
            matchesAuthRedirectString(
                "com.dawnchat.app://other/callback?ticket=a",
                "com.dawnchat.app://auth/callback",
            ),
        )
    }

    @Test
    fun parseDesktopAuthCallbackUrl_readsTicketAndState() {
        val p = parseDesktopAuthCallbackUrl("com.dawnchat.app://auth/callback?ticket=t1&state=s1")
        assertEquals("t1", p.ticket)
        assertEquals("s1", p.state)
        assertNull(p.error)
    }

    @Test
    fun parseDesktopAuthCallbackUrl_prefersErrorDescription() {
        val p = parseDesktopAuthCallbackUrl(
            "com.dawnchat.app://auth/callback?error=access_denied&error_description=no%20way",
        )
        assertEquals("no way", p.error)
    }

    @Test
    fun normalizeNextPath_defaultsForUnsafePath() {
        assertEquals("/app/workbench", normalizeNextPath("/steal/cookies"))
    }

    @Test
    fun normalizeNextPath_acceptsAppAndFullscreen() {
        assertEquals("/app/hub", normalizeNextPath("/app/hub"))
        assertEquals("/fullscreen/x", normalizeNextPath("/fullscreen/x"))
    }

    @Test
    fun jsonStringLiteral_escapesQuotesAndBackslash() {
        assertEquals("\"a\\\"b\\\\c\"", jsonStringLiteral("a\"b\\c"))
    }

    @Test
    fun buildExchangeRequestBody_matchesExpectedKeys() {
        val raw = buildExchangeRequestBody("t\"k", "s1", "d1")
        assertTrue(raw.contains("\"desktop_ticket\":\"t\\\"k\""))
        assertTrue(raw.contains("\"state\":\"s1\""))
        assertTrue(raw.contains("\"device_id\":\"d1\""))
        assertTrue(raw.contains("\"protocol_version\":\"1\""))
    }

    @Test
    fun parseExchangeSuccessResponse_readsTokens() {
        val r = parseExchangeSuccessResponse(
            """{"access_token":"aa.bb","refresh_token":"cc","expires_at":42,"extra":true}""",
        )
        assertTrue(r.isSuccess)
        val t = r.getOrThrow()
        assertEquals("aa.bb", t.accessToken)
        assertEquals("cc", t.refreshToken)
        assertEquals(42L, t.expiresAt)
    }
}
