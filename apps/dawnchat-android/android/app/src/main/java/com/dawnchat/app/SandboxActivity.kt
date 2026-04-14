package com.dawnchat.app

import android.os.Bundle
import android.content.res.ColorStateList
import android.graphics.Color
import android.util.Log
import android.view.Gravity
import android.widget.FrameLayout
import androidx.activity.OnBackPressedCallback
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.dawnchat.app.plugins.DawnTtsPlugin
import com.getcapacitor.BridgeActivity
import com.google.android.material.floatingactionbutton.FloatingActionButton

/**
 * Plugin Capacitor WebView only; host OAuth / ticket exchange lives in Kotlin ([com.dawnchat.app.auth]).
 */
class SandboxActivity : BridgeActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(DawnTtsPlugin::class.java)
        super.onCreate(savedInstanceState)
        attachFloatingCloseButton()
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (bridge?.webView?.canGoBack() == true) {
                    bridge?.webView?.goBack()
                } else {
                    finish()
                }
            }
        })
    }

    override fun load() {
        var targetUrl = intent.getStringExtra(EXTRA_TARGET_URL).orEmpty()
        val serverBasePath = intent.getStringExtra(EXTRA_SERVER_BASE_PATH).orEmpty()
        val pluginId = intent.getStringExtra(EXTRA_PLUGIN_ID).orEmpty()
        val offlineMode = serverBasePath.isNotBlank()

        if (targetUrl.endsWith("/")) {
            targetUrl = targetUrl.dropLast(1)
        }

        Log.i(
            TAG,
            "Sandbox load start mode=${if (offlineMode) "offline" else "hmr"} targetUrl=$targetUrl serverBasePath=$serverBasePath pluginId=$pluginId"
        )

        if (!offlineMode && targetUrl.isNotEmpty()) {
            if (this.config == null) {
                this.config = com.getcapacitor.CapConfig.loadDefault(this)
            }
            try {
                val serverUrlField = this.config.javaClass.getDeclaredField("serverUrl")
                serverUrlField.isAccessible = true
                serverUrlField.set(this.config, targetUrl)
                Log.i(TAG, "Injected config.serverUrl for HMR: $targetUrl")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to inject config.serverUrl: ${e.message}", e)
            }
        } else if (offlineMode) {
            Log.i(TAG, "Offline mode detected, skip custom serverUrl injection")
        }

        super.load()
        Log.i(
            TAG,
            "Bridge loaded appUrl=${bridge?.appUrl ?: ""} localUrl=${bridge?.localUrl ?: ""} requestedTarget=$targetUrl"
        )

        if (serverBasePath.isNotBlank()) {
            Log.i(TAG, "Apply offline server base path: $serverBasePath")
            bridge?.setServerBasePath(serverBasePath)
            bridge?.webView?.post {
                val resolvedUrl = bridge?.appUrl?.takeIf { it.isNotBlank() }
                    ?: bridge?.localUrl?.takeIf { it.isNotBlank() }
                    ?: targetUrl
                if (resolvedUrl.isBlank()) {
                    Log.w(TAG, "Skip offline reload because appUrl and targetUrl are both empty")
                    return@post
                }
                Log.i(TAG, "Offline reload url: $resolvedUrl")
                bridge?.webView?.loadUrl(resolvedUrl)
                bridge?.webView?.clearHistory()
            }
        }
    }

    private fun attachFloatingCloseButton() {
        val baseMargin = dpToPx(16)
        val closeButton = FloatingActionButton(this).apply {
            contentDescription = getString(R.string.action_close)
            setImageResource(android.R.drawable.ic_menu_close_clear_cancel)
            size = FloatingActionButton.SIZE_MINI
            backgroundTintList = ColorStateList.valueOf(Color.parseColor("#C0C0C0"))
            imageTintList = ColorStateList.valueOf(Color.parseColor("#333333"))
            compatElevation = dpToPx(6).toFloat()
            setOnClickListener { finish() }
        }
        val params = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            gravity = Gravity.TOP or Gravity.END
            setMargins(baseMargin, baseMargin, baseMargin, baseMargin)
        }
        addContentView(closeButton, params)

        ViewCompat.setOnApplyWindowInsetsListener(closeButton) { view, insets ->
            val safeInsets = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
            )
            val lp = view.layoutParams as FrameLayout.LayoutParams
            lp.topMargin = baseMargin + safeInsets.top
            lp.rightMargin = baseMargin + safeInsets.right
            view.layoutParams = lp
            insets
        }
        ViewCompat.requestApplyInsets(closeButton)
    }

    private fun dpToPx(dp: Int): Int {
        return (dp * resources.displayMetrics.density).toInt()
    }

    companion object {
        private const val TAG = "SandboxActivity"
        const val EXTRA_TARGET_URL = "TARGET_URL"
        const val EXTRA_SERVER_BASE_PATH = "SERVER_BASE_PATH"
        const val EXTRA_TITLE = "SANDBOX_TITLE"
        const val EXTRA_PLUGIN_ID = "PLUGIN_ID"
    }
}