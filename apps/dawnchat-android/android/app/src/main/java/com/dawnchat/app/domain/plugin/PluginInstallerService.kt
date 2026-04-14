package com.dawnchat.app.domain.plugin

import android.content.Context
import com.dawnchat.app.data.plugin.PluginMetadata
import com.dawnchat.app.data.plugin.PluginStorageService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import net.lingala.zip4j.ZipFile
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import java.time.format.DateTimeParseException
import java.util.concurrent.TimeUnit

class PluginInstallerService(
    context: Context,
    private val storageService: PluginStorageService = PluginStorageService(context),
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    suspend fun install(payload: BundlePayload): Result<PluginMetadata> = withContext(Dispatchers.IO) {
        runCatching {
            validateExpiry(payload.artifact.expiresAt)

            val paths = storageService.buildPaths(payload.plugin.id, payload.plugin.version)
            paths.tmpDir.deleteRecursively()
            paths.tmpDir.mkdirs()
            paths.tmpExtractDir.mkdirs()

            download(payload.artifact.url, paths.tmpZipFile)
            if (payload.artifact.size > 0) {
                require(paths.tmpZipFile.length() == payload.artifact.size) { "ZIP size mismatch" }
            }
            verifySha256(paths.tmpZipFile, payload.artifact.sha256)

            val extractRoot = unzipToTemp(paths.tmpZipFile, paths.tmpExtractDir, payload.plugin.entry)
            val targetVersionDir = File(paths.versionsDir, PluginStorageService.sanitizeSegment(payload.plugin.version))
            if (targetVersionDir.exists()) {
                targetVersionDir.deleteRecursively()
            }
            extractRoot.copyRecursively(targetVersionDir, overwrite = true)

            val metadata = PluginMetadata(
                pluginId = payload.plugin.id,
                name = payload.plugin.name,
                currentVersion = payload.plugin.version,
                entry = payload.plugin.entry,
                updatedAt = System.currentTimeMillis(),
                installStatus = PluginMetadata.STATUS_SUCCESS,
            )
            storageService.writeMetadata(metadata)

            paths.tmpDir.deleteRecursively()
            metadata
        }
    }

    private fun download(url: String, outputFile: File) {
        val request = Request.Builder().url(url).get().build()
        client.newCall(request).execute().use { response ->
            require(response.isSuccessful) { "Download failed: HTTP ${response.code}" }
            val body = response.body ?: error("Download failed: empty response body")
            outputFile.outputStream().use { output ->
                body.byteStream().copyTo(output)
            }
        }
    }

    private fun verifySha256(zipFile: File, expectedSha256: String) {
        val digest = MessageDigest.getInstance("SHA-256")
        zipFile.inputStream().buffered().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count <= 0) break
                digest.update(buffer, 0, count)
            }
        }
        val actual = digest.digest().joinToString("") { "%02x".format(it) }
        require(actual.equals(expectedSha256.lowercase(), ignoreCase = true)) {
            "SHA256 mismatch"
        }
    }

    private fun unzipToTemp(zipFile: File, extractDir: File, entry: String): File {
        val zip = ZipFile(zipFile)
        val extractCanonical = extractDir.canonicalPath
        zip.fileHeaders.forEach { header ->
            val outFile = File(extractDir, header.fileName)
            val outCanonical = outFile.canonicalPath
            require(
                outCanonical == extractCanonical || outCanonical.startsWith("$extractCanonical${File.separator}")
            ) { "Unsafe zip entry detected" }
        }

        zip.extractAll(extractDir.absolutePath)

        val rootEntry = File(extractDir, entry)
        if (rootEntry.exists()) return extractDir

        val firstChildDir = extractDir.listFiles()
            ?.firstOrNull { it.isDirectory && File(it, entry).exists() }
            ?: error("Entry file not found after extraction: $entry")
        return firstChildDir
    }

    private fun validateExpiry(expiresAt: String?) {
        if (expiresAt.isNullOrBlank()) return
        try {
            val expires = Instant.parse(expiresAt)
            require(!expires.isBefore(Instant.now())) { "Artifact URL expired" }
        } catch (e: DateTimeParseException) {
            error("Invalid expiresAt format")
        }
    }
}
