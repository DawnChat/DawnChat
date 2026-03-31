import UIKit
import Capacitor

enum SandboxLaunchTarget {
    case hmr(url: URL)
    case offline(config: OfflinePluginLaunch)
}

struct OfflinePluginLaunch {
    let pluginId: String
    let pluginName: String
    let version: String
    let serverURL: URL
    let localBasePath: URL
    let entry: String
}

final class SandboxViewController: CAPBridgeViewController {
    var launchTarget: SandboxLaunchTarget = .hmr(url: URL(string: "https://example.com")!)
    private let closeButton: UIButton = {
        var config = UIButton.Configuration.filled()
        config.image = UIImage(systemName: "xmark")
        config.baseForegroundColor = .systemGray
        config.baseBackgroundColor = UIColor.systemGray5.withAlphaComponent(0.95)
        config.cornerStyle = .capsule
        config.contentInsets = NSDirectionalEdgeInsets(top: 10, leading: 10, bottom: 10, trailing: 10)

        let button = UIButton(type: .system)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.configuration = config
        button.accessibilityLabel = "关闭插件"
        button.accessibilityHint = "关闭当前插件沙箱页面"
        return button
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        setupFloatingCloseButton()
        loadTarget()
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        navigationController?.setNavigationBarHidden(true, animated: animated)
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        navigationController?.setNavigationBarHidden(false, animated: animated)
    }

    private func setupFloatingCloseButton() {
        view.addSubview(closeButton)
        view.bringSubviewToFront(closeButton)
        closeButton.addTarget(self, action: #selector(closeSandbox), for: .touchUpInside)

        NSLayoutConstraint.activate([
            closeButton.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
            closeButton.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -12),
            closeButton.widthAnchor.constraint(equalToConstant: 42),
            closeButton.heightAnchor.constraint(equalToConstant: 42)
        ])
    }

    private func loadTarget() {
        switch launchTarget {
        case .hmr(let url):
            webView?.load(URLRequest(url: url))
        case .offline(let config):
            // Use CAPBridgeViewController's reload helper so local asset mapping and reload
            // happen with the same flow as Capacitor Updater.
            setServerBasePath(path: config.localBasePath.path)
            loadOfflineEntryIfNeeded(config)
        }
    }

    private func loadOfflineEntryIfNeeded(_ config: OfflinePluginLaunch) {
        let normalizedEntry = config.entry.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard !normalizedEntry.isEmpty, normalizedEntry != "index.html" else {
            return
        }
        guard let baseURL = bridge?.config.serverURL else {
            return
        }
        if let entryURL = URL(string: normalizedEntry, relativeTo: baseURL)?.absoluteURL {
            webView?.load(URLRequest(url: entryURL))
        }
    }

    @objc private func closeSandbox() {
        dismiss(animated: true)
    }
}
