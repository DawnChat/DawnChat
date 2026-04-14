package com.dawnchat.app.ui.scan

import android.content.Intent
import android.content.pm.ActivityInfo
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.journeyapps.barcodescanner.ScanOptions

class ScanActivity : AppCompatActivity() {

    private var scanStarted = false

    private val barcodeLauncher = registerForActivityResult(ScanContract()) { result: ScanIntentResult ->
        val contents = result.contents
        if (!contents.isNullOrBlank()) {
            setResult(
                RESULT_OK,
                Intent().putExtra(EXTRA_SCAN_RESULT, contents)
            )
        } else {
            setResult(RESULT_CANCELED)
        }
        finish()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        scanStarted = savedInstanceState?.getBoolean(KEY_SCAN_STARTED) ?: false
        if (!scanStarted) {
            startScanner()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean(KEY_SCAN_STARTED, scanStarted)
    }

    private fun startScanner() {
        scanStarted = true
        val options = ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            setPrompt("请扫描 DawnChat 插件二维码")
            setCameraId(0)
            setBeepEnabled(true)
            setOrientationLocked(true)
            setCaptureActivity(PortraitCaptureActivity::class.java)
            setBarcodeImageEnabled(false)
        }
        barcodeLauncher.launch(options)
    }

    companion object {
        const val EXTRA_SCAN_RESULT = "SCAN_RESULT"
        private const val KEY_SCAN_STARTED = "scan_started"
    }
}
