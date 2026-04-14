package com.dawnchat.app.auth

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.browser.customtabs.CustomTabsIntent
import androidx.lifecycle.lifecycleScope
import com.dawnchat.app.MainActivity
import com.dawnchat.app.R
import com.google.android.material.button.MaterialButton
import com.google.android.material.progressindicator.LinearProgressIndicator
import kotlinx.coroutines.launch

/**
 * Native-only login: opens system browser (Custom Tabs) to the official desktop-auth bridge.
 * Deep link return is handled here (and in [MainActivity]) in Kotlin — not in WebView.
 */
class NativeLoginActivity : AppCompatActivity() {

    private lateinit var repo: MobileAuthRepository
    private lateinit var statusText: TextView
    private lateinit var progress: LinearProgressIndicator
    private lateinit var loginButton: MaterialButton

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_native_login)
        repo = MobileAuthRepository(this)
        statusText = findViewById(R.id.textAuthStatus)
        progress = findViewById(R.id.progressAuth)
        loginButton = findViewById(R.id.buttonStartWebLogin)

        loginButton.setOnClickListener { startBrowserLogin() }
        processIntentData(intent)
        lifecycleScope.launch {
            val uri = intent?.data
            if (uri != null && repo.matchesAuthRedirect(uri)) return@launch
            if (repo.awaitSessionVerifiedForLaunch()) {
                goToMain()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        processIntentData(intent)
    }

    private fun processIntentData(intent: Intent?) {
        val uri = intent?.data ?: return
        if (!repo.matchesAuthRedirect(uri)) return
        progress.visibility = View.VISIBLE
        progress.isIndeterminate = true
        loginButton.isEnabled = false
        lifecycleScope.launch {
            val result = repo.completeAuthFromCallback(uri)
            progress.visibility = View.GONE
            loginButton.isEnabled = true
            result.fold(
                onSuccess = {
                    goToMain()
                },
                onFailure = { e ->
                    val msg = e.message ?: "登录失败"
                    statusText.text = msg
                    Toast.makeText(this@NativeLoginActivity, msg, Toast.LENGTH_LONG).show()
                },
            )
        }
    }

    private fun startBrowserLogin() {
        if (!repo.isConfigReady()) {
            val msg = getString(R.string.auth_missing_supabase_config)
            statusText.text = msg
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
            return
        }
        try {
            val url = repo.prepareBridgeLogin()
            val tabs = CustomTabsIntent.Builder().build()
            tabs.launchUrl(this, Uri.parse(url))
            statusText.text = getString(R.string.auth_waiting_browser_return)
        } catch (e: Exception) {
            val msg = e.message ?: getString(R.string.auth_bridge_url_failed)
            statusText.text = msg
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
        }
    }

    private fun goToMain() {
        startActivity(
            Intent(this, MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            },
        )
        finish()
    }
}
