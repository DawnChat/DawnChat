package com.dawnchat.app.ui.main

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.dawnchat.app.R
import com.dawnchat.app.SandboxActivity
import com.dawnchat.app.builtin.BuiltinMobileAssistant
import com.dawnchat.app.builtin.BuiltinPluginSeeder
import com.dawnchat.app.builtin.HostBuiltinAssistantPrefs
import com.dawnchat.app.data.plugin.PluginMetadata
import com.dawnchat.app.data.plugin.PluginStorageService
import com.dawnchat.app.domain.plugin.PluginInstallerService
import com.dawnchat.app.domain.plugin.PluginPayloadParser
import com.dawnchat.app.domain.plugin.ScanPayload
import com.dawnchat.app.ui.scan.ScanActivity
import com.google.android.material.appbar.MaterialToolbar
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class HomeFragment : Fragment() {

    private lateinit var toolbar: MaterialToolbar
    private lateinit var recyclerView: RecyclerView
    private lateinit var emptyText: TextView
    private lateinit var progressBar: ProgressBar

    private lateinit var storageService: PluginStorageService
    private lateinit var installerService: PluginInstallerService
    private val parser = PluginPayloadParser()
    private val adapter = PluginAdapter { metadata -> launchOfflineSandbox(metadata) }

    private val scanLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == android.app.Activity.RESULT_OK) {
            val rawText = result.data?.getStringExtra(ScanActivity.EXTRA_SCAN_RESULT).orEmpty()
            handleScanResult(rawText)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val appContext = requireContext().applicationContext
        storageService = PluginStorageService(appContext)
        installerService = PluginInstallerService(appContext, storageService)
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?,
    ): View {
        return inflater.inflate(R.layout.fragment_home, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        toolbar = view.findViewById(R.id.toolbarHome)
        recyclerView = view.findViewById(R.id.recyclerPlugins)
        emptyText = view.findViewById(R.id.textEmptyPlugins)
        progressBar = view.findViewById(R.id.progressInstall)

        toolbar.title = getString(R.string.tab_home)
        toolbar.inflateMenu(R.menu.menu_home_toolbar)
        toolbar.setOnMenuItemClickListener(::onToolbarMenuClick)

        recyclerView.layoutManager = GridLayoutManager(requireContext(), 2)
        recyclerView.adapter = adapter

        refreshPlugins()
    }

    override fun onResume() {
        super.onResume()
        viewLifecycleOwner.lifecycleScope.launch {
            BuiltinPluginSeeder.seedIfNeeded(requireContext().applicationContext)
            withContext(Dispatchers.Main) {
                refreshPlugins()
                maybeAutoLaunchBuiltinAssistant()
            }
        }
    }

    private fun maybeAutoLaunchBuiltinAssistant() {
        val ctx = requireContext().applicationContext
        if (!HostBuiltinAssistantPrefs.isAutoOpenEnabled(ctx)) return
        val catalogVersion = BuiltinPluginSeeder.embeddedCatalogVersion(ctx)
        if (HostBuiltinAssistantPrefs.autoOpenedEmbeddedVersion(ctx) == catalogVersion) return
        val meta = storageService.readMetadata(BuiltinMobileAssistant.PLUGIN_ID) ?: return
        if (meta.currentVersion != catalogVersion) return
        val versionDir = storageService.getVersionDir(meta.pluginId, meta.currentVersion)
        if (!File(versionDir, meta.entry).isFile) return
        HostBuiltinAssistantPrefs.setAutoOpenedEmbeddedVersion(ctx, catalogVersion)
        launchOfflineSandbox(meta)
    }

    private fun onToolbarMenuClick(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_scan -> {
                scanLauncher.launch(Intent(requireContext(), ScanActivity::class.java))
                true
            }

            else -> false
        }
    }

    private fun handleScanResult(rawText: String) {
        if (rawText.isBlank()) return
        parser.parse(rawText)
            .onSuccess { payload ->
                when (payload) {
                    is ScanPayload.Hmr -> launchHmrSandbox(payload.url)
                    is ScanPayload.Bundle -> installBundle(payload)
                }
            }
            .onFailure {
                Toast.makeText(requireContext(), getString(R.string.qr_invalid_payload), Toast.LENGTH_LONG).show()
            }
    }

    private fun installBundle(payload: ScanPayload.Bundle) {
        progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            installerService.install(payload.payload)
                .onSuccess { metadata ->
                    progressBar.visibility = View.GONE
                    HostBuiltinAssistantPrefs.markExternalInstall(requireContext().applicationContext, metadata.pluginId)
                    refreshPlugins()
                    Toast.makeText(
                        requireContext(),
                        getString(R.string.install_success, metadata.name),
                        Toast.LENGTH_SHORT
                    ).show()
                    launchOfflineSandbox(metadata)
                }
                .onFailure { throwable ->
                    progressBar.visibility = View.GONE
                    Toast.makeText(
                        requireContext(),
                        getString(R.string.install_failed, throwable.message ?: ""),
                        Toast.LENGTH_LONG
                    ).show()
                    Log.e("HomeFragment", throwable.message?:"")
                }
        }
    }

    private fun launchHmrSandbox(url: String) {
        val intent = Intent(requireContext(), SandboxActivity::class.java).apply {
            putExtra(SandboxActivity.EXTRA_TARGET_URL, url)
            putExtra(SandboxActivity.EXTRA_TITLE, getString(R.string.sandbox_title_hmr))
        }
        startActivity(intent)
    }

    private fun launchOfflineSandbox(metadata: PluginMetadata) {
        val versionDir = storageService.getVersionDir(metadata.pluginId, metadata.currentVersion)
        if (!versionDir.exists()) {
            Toast.makeText(requireContext(), R.string.plugin_files_missing, Toast.LENGTH_LONG).show()
            return
        }
        val intent = Intent(requireContext(), SandboxActivity::class.java).apply {
            // Android offline bundle uses Capacitor local server + serverBasePath directly.
            // Avoid custom virtual domain here to prevent unresolved host fallback on some devices.
            putExtra(SandboxActivity.EXTRA_SERVER_BASE_PATH, versionDir.absolutePath)
            putExtra(SandboxActivity.EXTRA_TITLE, metadata.name)
            putExtra(SandboxActivity.EXTRA_PLUGIN_ID, metadata.pluginId)
        }
        startActivity(intent)
    }

    private fun refreshPlugins() {
        val plugins = storageService.listPlugins()
        adapter.submitList(plugins)
        emptyText.visibility = if (plugins.isEmpty()) View.VISIBLE else View.GONE
    }

    companion object {
        const val TAG = "HomeFragment"
    }
}
