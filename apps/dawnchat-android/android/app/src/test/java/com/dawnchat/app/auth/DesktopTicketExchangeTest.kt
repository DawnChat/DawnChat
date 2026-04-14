package com.dawnchat.app.auth

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

class DesktopTicketExchangeTest {

    private lateinit var server: MockWebServer
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .writeTimeout(5, TimeUnit.SECONDS)
        .build()

    @Before
    fun setup() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun exchange_postsExpectedJsonAndReturnsTokens() {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("""{"access_token":"acc","refresh_token":"ref","expires_at":999}"""),
        )
        val base = server.url("").toString().trimEnd('/')
        val result = exchangeDesktopTicket(
            client,
            base,
            anonKey = "anon-test",
            ticket = "tick",
            state = "dc_state",
            deviceId = "dev-1",
        )
        assertTrue(result.isSuccess)
        val tokens = result.getOrThrow()
        assertEquals("acc", tokens.accessToken)
        assertEquals("ref", tokens.refreshToken)
        assertEquals(999L, tokens.expiresAt)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertTrue(recorded.path!!.endsWith("/functions/v1/exchange-desktop-ticket"))
        assertEquals("anon-test", recorded.getHeader("apikey"))
        val bodyRaw = recorded.body.readUtf8()
        assertTrue(bodyRaw.contains("\"desktop_ticket\":\"tick\""))
        assertTrue(bodyRaw.contains("\"state\":\"dc_state\""))
        assertTrue(bodyRaw.contains("\"device_id\":\"dev-1\""))
        assertTrue(bodyRaw.contains("\"protocol_version\":\"1\""))
    }

    @Test
    fun exchange_mapsErrorBody() {
        server.enqueue(
            MockResponse()
                .setResponseCode(401)
                .setBody("""{"message":"state_mismatch"}"""),
        )
        val base = server.url("").toString().trimEnd('/')
        val result = exchangeDesktopTicket(client, base, "k", "t", "s", "d")
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message?.contains("state_mismatch") == true)
    }
}
