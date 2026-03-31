import UIKit
import AVFoundation
import CryptoKit
import ZIPFoundation

final class LobbyViewController: UIViewController {
    private let storage = PluginStorageService.shared
    private lazy var installer = PluginInstallerService(storage: storage)

    private var plugins: [InstalledPluginSummary] = []
    private lazy var collectionView: UICollectionView = {
        let view = UICollectionView(frame: .zero, collectionViewLayout: createLayout())
        view.translatesAutoresizingMaskIntoConstraints = false
        view.backgroundColor = .systemBackground
        view.delegate = self
        view.dataSource = self
        view.register(PluginCardCell.self, forCellWithReuseIdentifier: PluginCardCell.reuseID)
        return view
    }()

    private let emptyLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.textAlignment = .center
        label.textColor = .secondaryLabel
        label.numberOfLines = 0
        label.text = "暂无已下载插件\n点击右上角扫码导入"
        return label
    }()

    private let loadingOverlay = LoadingOverlayView()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = L10n.text("tab.home")
        navigationController?.navigationBar.prefersLargeTitles = true
        setupNavigationBar()
        setupLayout()
        reloadPlugins()
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        reloadPlugins()
    }

    private func setupNavigationBar() {
        let scanItem = UIBarButtonItem(
            image: UIImage(systemName: "qrcode.viewfinder"),
            style: .plain,
            target: self,
            action: #selector(openScanner)
        )
        navigationItem.rightBarButtonItem = scanItem
    }

    private func setupLayout() {
        view.addSubview(collectionView)
        view.addSubview(emptyLabel)

        NSLayoutConstraint.activate([
            collectionView.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            collectionView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            collectionView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            collectionView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            emptyLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            emptyLabel.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            emptyLabel.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            emptyLabel.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24)
        ])
    }

    private func createLayout() -> UICollectionViewLayout {
        let itemSize = NSCollectionLayoutSize(
            widthDimension: .fractionalWidth(0.5),
            heightDimension: .estimated(132)
        )
        let item = NSCollectionLayoutItem(layoutSize: itemSize)
        item.contentInsets = NSDirectionalEdgeInsets(top: 8, leading: 8, bottom: 8, trailing: 8)
        let groupSize = NSCollectionLayoutSize(
            widthDimension: .fractionalWidth(1.0),
            heightDimension: .estimated(132)
        )
        let group = NSCollectionLayoutGroup.horizontal(layoutSize: groupSize, subitems: [item, item])
        let section = NSCollectionLayoutSection(group: group)
        section.contentInsets = NSDirectionalEdgeInsets(top: 8, leading: 8, bottom: 24, trailing: 8)
        return UICollectionViewCompositionalLayout(section: section)
    }

    private func reloadPlugins() {
        plugins = storage.installedPlugins()
        emptyLabel.isHidden = !plugins.isEmpty
        collectionView.reloadData()
    }

    @objc private func openScanner() {
        let scanner = ScannerViewController()
        scanner.onScannedResult = { [weak self] rawCode in
            self?.handleScanResult(rawCode)
        }
        navigationController?.pushViewController(scanner, animated: true)
    }

    private func handleScanResult(_ rawCode: String) {
        do {
            let parsed = try PluginPayloadParser.parse(rawCode)
            switch parsed {
            case .hmr(let url):
                presentSandbox(.hmr(url: url))
            case .bundle(let payload):
                loadingOverlay.show(in: view, text: "正在安装插件...")
                Task {
                    do {
                        let summary = try await installer.install(payload: payload)
                        await MainActor.run {
                            loadingOverlay.hide()
                            reloadPlugins()
                            let launch = storage.makeOfflineLaunch(for: summary)
                            presentSandbox(.offline(config: launch))
                        }
                    } catch {
                        await MainActor.run {
                            loadingOverlay.hide()
                            showError(message: error.localizedDescription)
                        }
                    }
                }
            }
        } catch {
            showError(message: error.localizedDescription)
        }
    }

    private func presentSandbox(_ target: SandboxLaunchTarget) {
        let sandbox = SandboxViewController()
        sandbox.launchTarget = target
        let nav = UINavigationController(rootViewController: sandbox)
        nav.modalPresentationStyle = .fullScreen
        present(nav, animated: true)
    }

    private func showError(message: String) {
        let alert = UIAlertController(title: "处理失败", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: L10n.text("common.ok"), style: .default))
        present(alert, animated: true)
    }
}

extension LobbyViewController: UICollectionViewDataSource, UICollectionViewDelegate {
    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int {
        plugins.count
    }

    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: PluginCardCell.reuseID, for: indexPath)
        if let pluginCell = cell as? PluginCardCell {
            pluginCell.configure(with: plugins[indexPath.item])
        }
        return cell
    }

    func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        let plugin = plugins[indexPath.item]
        let config = storage.makeOfflineLaunch(for: plugin)
        presentSandbox(.offline(config: config))
    }
}

final class PluginCardCell: UICollectionViewCell {
    static let reuseID = "PluginCardCell"

    private let nameLabel = UILabel()
    private let versionLabel = UILabel()
    private let updateLabel = UILabel()

    override init(frame: CGRect) {
        super.init(frame: frame)
        contentView.backgroundColor = .secondarySystemBackground
        contentView.layer.cornerRadius = 14

        nameLabel.font = .systemFont(ofSize: 16, weight: .semibold)
        nameLabel.numberOfLines = 2
        versionLabel.font = .systemFont(ofSize: 13, weight: .medium)
        versionLabel.textColor = .secondaryLabel
        updateLabel.font = .systemFont(ofSize: 12, weight: .regular)
        updateLabel.textColor = .tertiaryLabel

        let stack = UIStackView(arrangedSubviews: [nameLabel, versionLabel, updateLabel])
        stack.axis = .vertical
        stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(stack)

        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: contentView.bottomAnchor, constant: -12)
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with item: InstalledPluginSummary) {
        nameLabel.text = item.name
        versionLabel.text = "v\(item.version)"
        updateLabel.text = item.updatedAt.formatted(date: .numeric, time: .shortened)
    }
}

final class LoadingOverlayView: UIView {
    private let indicator = UIActivityIndicatorView(style: .large)
    private let label = UILabel()

    init() {
        super.init(frame: .zero)
        backgroundColor = UIColor.black.withAlphaComponent(0.35)
        translatesAutoresizingMaskIntoConstraints = false

        indicator.translatesAutoresizingMaskIntoConstraints = false
        indicator.startAnimating()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.textColor = .white
        label.font = .systemFont(ofSize: 14, weight: .medium)

        addSubview(indicator)
        addSubview(label)

        NSLayoutConstraint.activate([
            indicator.centerXAnchor.constraint(equalTo: centerXAnchor),
            indicator.centerYAnchor.constraint(equalTo: centerYAnchor, constant: -10),
            label.centerXAnchor.constraint(equalTo: centerXAnchor),
            label.topAnchor.constraint(equalTo: indicator.bottomAnchor, constant: 10)
        ])
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func show(in parent: UIView, text: String) {
        label.text = text
        if superview == nil {
            parent.addSubview(self)
            NSLayoutConstraint.activate([
                topAnchor.constraint(equalTo: parent.topAnchor),
                leadingAnchor.constraint(equalTo: parent.leadingAnchor),
                trailingAnchor.constraint(equalTo: parent.trailingAnchor),
                bottomAnchor.constraint(equalTo: parent.bottomAnchor)
            ])
        }
    }

    func hide() {
        removeFromSuperview()
    }
}

final class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onScannedResult: ((String) -> Void)?

    private var captureSession: AVCaptureSession?
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var hasHandledResult = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        title = "扫码"
        setupScanner()
    }
        
    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        captureSession?.stopRunning()
    }

    private func setupScanner() {
        #if targetEnvironment(simulator)
        showSimulatorFallback()
        #else
        requestCameraAndStart()
        #endif
    }

    #if targetEnvironment(simulator)
    private func showSimulatorFallback() {
        view.backgroundColor = .systemBackground
        let button = UIButton(type: .system)
        button.setTitle("模拟器输入二维码文本", for: .normal)
        button.addTarget(self, action: #selector(promptSimulatorCode), for: .touchUpInside)
        button.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(button)
        NSLayoutConstraint.activate([
            button.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            button.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }

    @objc private func promptSimulatorCode() {
        let alert = UIAlertController(title: "输入二维码内容", message: nil, preferredStyle: .alert)
        alert.addTextField { textField in
            textField.placeholder = "http://192.168.1.100:5173 或 JSON"
        }
        alert.addAction(UIAlertAction(title: "取消", style: .cancel))
        alert.addAction(UIAlertAction(title: "确认", style: .default, handler: { [weak self] _ in
            guard let text = alert.textFields?.first?.text, !text.isEmpty else { return }
            self?.finishWithCode(text)
        }))
        present(alert, animated: true)
    }
    #endif

    private func requestCameraAndStart() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            configureCaptureSession()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    granted ? self?.configureCaptureSession() : self?.showPermissionDenied()
                }
            }
        default:
            showPermissionDenied()
        }
    }

    private func configureCaptureSession() {
        let session = AVCaptureSession()
        guard
            let videoDevice = AVCaptureDevice.default(for: .video),
            let input = try? AVCaptureDeviceInput(device: videoDevice),
            session.canAddInput(input)
        else {
            showFailure("无法初始化相机输入")
            return
        }
        session.addInput(input)

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else {
            showFailure("无法初始化扫码输出")
            return
        }
        session.addOutput(output)
        output.metadataObjectTypes = [.qr]
        output.setMetadataObjectsDelegate(self, queue: .main)

        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.bounds
        view.layer.insertSublayer(layer, at: 0)

        captureSession = session
        previewLayer = layer

        DispatchQueue.global(qos: .userInitiated).async {
            session.startRunning()
        }
    }

    private func showPermissionDenied() {
        let alert = UIAlertController(
            title: "相机权限未开启",
            message: "请在系统设置中允许 DawnChatDev 使用相机后重试。",
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: L10n.text("common.ok"), style: .default))
        present(alert, animated: true)
    }

    private func showFailure(_ message: String) {
        let alert = UIAlertController(title: "扫码初始化失败", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: L10n.text("common.ok"), style: .default))
        present(alert, animated: true)
    }

    func metadataOutput(
        _ output: AVCaptureMetadataOutput,
        didOutput metadataObjects: [AVMetadataObject],
        from connection: AVCaptureConnection
    ) {
        guard
            !hasHandledResult,
            let metadata = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
            let text = metadata.stringValue
        else { return }
        hasHandledResult = true
            captureSession?.stopRunning()
        finishWithCode(text)
    }

    private func finishWithCode(_ code: String) {
        onScannedResult?(code)
        navigationController?.popViewController(animated: true)
    }
}

enum PayloadParseError: LocalizedError {
    case invalidFormat
    case unsupportedType

    var errorDescription: String? {
        switch self {
        case .invalidFormat:
            return "二维码格式不受支持"
        case .unsupportedType:
            return "二维码类型不支持"
        }
    }
}

enum PluginPayload {
    case hmr(url: URL)
    case bundle(payload: PluginBundlePayload)
}

struct PluginBundlePayload: Codable {
    struct PluginInfo: Codable {
        let id: String
        let name: String
        let version: String
        let entry: String?
    }

    struct ArtifactInfo: Codable {
        let url: String
        let sha256: String
        let size: Int?
        let expiresAt: String?
    }

    let schema: String
    let type: String
    let plugin: PluginInfo
    let artifact: ArtifactInfo
    let issuedAt: String?
}

enum PluginPayloadParser {
    static func parse(_ rawCode: String) throws -> PluginPayload {
        let cleaned = rawCode.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: cleaned), let scheme = url.scheme?.lowercased(), ["http", "https"].contains(scheme) {
            return .hmr(url: url)
        }

        guard let data = cleaned.data(using: .utf8) else {
            throw PayloadParseError.invalidFormat
        }
        let decoded = try JSONDecoder().decode(PluginBundlePayload.self, from: data)
        guard decoded.schema == "dawnchat.mobile.plugin.v1", decoded.type == "bundle" else {
            throw PayloadParseError.unsupportedType
        }
        return .bundle(payload: decoded)
    }
}

struct PluginMetadata: Codable {
    let pluginId: String
    var name: String
    var currentVersion: String
    var entry: String
    var updatedAt: Date
    var lastInstallStatus: String
}

struct InstalledPluginSummary {
    let pluginId: String
    let name: String
    let version: String
    let entry: String
    let basePath: URL
    let updatedAt: Date
}

enum PluginInstallError: LocalizedError {
    case expiredURL
    case invalidURL
    case checksumMismatch
    case missingEntryFile
    case extractionFailed

    var errorDescription: String? {
        switch self {
        case .expiredURL:
            return "插件下载链接已过期"
        case .invalidURL:
            return "插件下载地址无效"
        case .checksumMismatch:
            return "插件包校验失败"
        case .missingEntryFile:
            return "插件入口文件不存在"
        case .extractionFailed:
            return "插件解压失败"
        }
    }
}

final class PluginStorageService {
    static let shared = PluginStorageService()
    private let fileManager = FileManager.default

    private init() {}

    private var rootDirectory: URL {
        let appSupport = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return appSupport.appendingPathComponent("DawnChatMobile/plugins", isDirectory: true)
    }

    func installedPlugins() -> [InstalledPluginSummary] {
        ensureRootDirectory()
        guard let pluginDirs = try? fileManager.contentsOfDirectory(
            at: rootDirectory,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }

        return pluginDirs.compactMap { dir in
            let metadataURL = dir.appendingPathComponent("metadata.json")
            guard let data = try? Data(contentsOf: metadataURL),
                  let metadata = try? JSONDecoder().decode(PluginMetadata.self, from: data) else { return nil }
            let basePath = dir.appendingPathComponent("versions/\(metadata.currentVersion)", isDirectory: true)
            guard fileManager.fileExists(atPath: basePath.path) else { return nil }
            return InstalledPluginSummary(
                pluginId: metadata.pluginId,
                name: metadata.name,
                version: metadata.currentVersion,
                entry: metadata.entry,
                basePath: basePath,
                updatedAt: metadata.updatedAt
            )
        }
        .sorted(by: { $0.updatedAt > $1.updatedAt })
    }

    func makeOfflineLaunch(for summary: InstalledPluginSummary) -> OfflinePluginLaunch {
        let host = "\(buildOfflineHostLabel(pluginId: summary.pluginId)).dawnchat.local"
        let serverURL = URL(string: "https://\(host)")!
        return OfflinePluginLaunch(
            pluginId: summary.pluginId,
            pluginName: summary.name,
            version: summary.version,
            serverURL: serverURL,
            localBasePath: summary.basePath,
            entry: summary.entry
        )
    }

    private func buildOfflineHostLabel(pluginId: String) -> String {
        let lowered = pluginId.lowercased()
        let normalized = lowered.replacingOccurrences(
            of: "[^a-z0-9-]",
            with: "-",
            options: .regularExpression
        )
        let collapsed = normalized.replacingOccurrences(
            of: "-+",
            with: "-",
            options: .regularExpression
        )
        let trimmed = collapsed.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return "plugin-\(trimmed.isEmpty ? "plugin" : trimmed)"
    }

    func prepareInstallPaths(pluginId: String, version: String) throws -> (pluginDir: URL, tempZip: URL, tempExtract: URL, finalVersionDir: URL) {
        ensureRootDirectory()
        let pluginDir = rootDirectory.appendingPathComponent(safePluginId(pluginId), isDirectory: true)
        let tmpDir = pluginDir.appendingPathComponent("tmp", isDirectory: true)
        let versionsDir = pluginDir.appendingPathComponent("versions", isDirectory: true)
        let tempZip = tmpDir.appendingPathComponent("bundle.zip")
        let tempExtract = tmpDir.appendingPathComponent("extract", isDirectory: true)
        let finalVersionDir = versionsDir.appendingPathComponent(version, isDirectory: true)

        try fileManager.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: versionsDir, withIntermediateDirectories: true)

        if fileManager.fileExists(atPath: tempExtract.path) {
            try fileManager.removeItem(at: tempExtract)
        }
        try fileManager.createDirectory(at: tempExtract, withIntermediateDirectories: true)

        return (pluginDir, tempZip, tempExtract, finalVersionDir)
    }

    func commitInstall(
        payload: PluginBundlePayload,
        extractedDirectory: URL,
        finalDirectory: URL,
        pluginDirectory: URL
    ) throws -> InstalledPluginSummary {
        let entry = payload.plugin.entry ?? "index.html"
        let entryURL = extractedDirectory.appendingPathComponent(entry)
        guard fileManager.fileExists(atPath: entryURL.path) else {
            throw PluginInstallError.missingEntryFile
        }

        if fileManager.fileExists(atPath: finalDirectory.path) {
            try fileManager.removeItem(at: finalDirectory)
        }
        try fileManager.moveItem(at: extractedDirectory, to: finalDirectory)

        let metadata = PluginMetadata(
            pluginId: payload.plugin.id,
            name: payload.plugin.name,
            currentVersion: payload.plugin.version,
            entry: entry,
            updatedAt: Date(),
            lastInstallStatus: "success"
        )
        let metadataURL = pluginDirectory.appendingPathComponent("metadata.json")
        let data = try JSONEncoder().encode(metadata)
        try data.write(to: metadataURL, options: [.atomic])

        return InstalledPluginSummary(
            pluginId: metadata.pluginId,
            name: metadata.name,
            version: metadata.currentVersion,
            entry: metadata.entry,
            basePath: finalDirectory,
            updatedAt: metadata.updatedAt
        )
    }

    private func ensureRootDirectory() {
        if !fileManager.fileExists(atPath: rootDirectory.path) {
            try? fileManager.createDirectory(at: rootDirectory, withIntermediateDirectories: true)
        }
    }

    private func safePluginId(_ pluginId: String) -> String {
        pluginId.replacingOccurrences(of: "[^a-zA-Z0-9._-]", with: "_", options: .regularExpression)
    }
}

final class PluginInstallerService {
    private let storage: PluginStorageService
    private let fileManager = FileManager.default
    private let iso8601 = ISO8601DateFormatter()

    init(storage: PluginStorageService) {
        self.storage = storage
    }

    func install(payload: PluginBundlePayload) async throws -> InstalledPluginSummary {
        if let expiresAt = payload.artifact.expiresAt,
           let expiryDate = iso8601.date(from: expiresAt),
           expiryDate < Date() {
            throw PluginInstallError.expiredURL
        }

        guard let zipURL = URL(string: payload.artifact.url) else {
            throw PluginInstallError.invalidURL
        }

        let paths = try storage.prepareInstallPaths(pluginId: payload.plugin.id, version: payload.plugin.version)
        let (downloadedURL, _) = try await URLSession.shared.download(from: zipURL)

        if fileManager.fileExists(atPath: paths.tempZip.path) {
            try fileManager.removeItem(at: paths.tempZip)
        }
        try fileManager.moveItem(at: downloadedURL, to: paths.tempZip)

        let digest = try sha256Hex(of: paths.tempZip)
        if digest.lowercased() != payload.artifact.sha256.lowercased() {
            throw PluginInstallError.checksumMismatch
        }

        try unzip(at: paths.tempZip, to: paths.tempExtract)
        return try storage.commitInstall(
            payload: payload,
            extractedDirectory: paths.tempExtract,
            finalDirectory: paths.finalVersionDir,
            pluginDirectory: paths.pluginDir
        )
    }

    private func sha256Hex(of fileURL: URL) throws -> String {
        let data = try Data(contentsOf: fileURL)
        let hash = SHA256.hash(data: data)
        return hash.compactMap { String(format: "%02x", $0) }.joined()
    }

    private func unzip(at zipURL: URL, to destination: URL) throws {
        guard let archive = Archive(url: zipURL, accessMode: .read) else {
            throw PluginInstallError.extractionFailed
        }

        for entry in archive {
            let entryDestination = destination.appendingPathComponent(entry.path)
            if entry.type == .directory {
                try fileManager.createDirectory(at: entryDestination, withIntermediateDirectories: true)
                continue
            }
            let parent = entryDestination.deletingLastPathComponent()
            try fileManager.createDirectory(at: parent, withIntermediateDirectories: true)
            _ = try archive.extract(entry, to: entryDestination)
        }
    }
}
