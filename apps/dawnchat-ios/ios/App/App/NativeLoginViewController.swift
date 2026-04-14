import AuthenticationServices
import UIKit

extension Notification.Name {
    static let dawnchatAuthCallbackURL = Notification.Name("dawnchatAuthCallbackURL")
}

/// Host-native login: system web session ([ASWebAuthenticationSession]) to the official bridge; ticket exchange in Swift.
final class NativeLoginViewController: UIViewController, ASWebAuthenticationPresentationContextProviding {

    private let scrollView: UIScrollView = {
        let s = UIScrollView()
        s.translatesAutoresizingMaskIntoConstraints = false
        s.alwaysBounceVertical = true
        return s
    }()

    private let contentStack: UIStackView = {
        let s = UIStackView()
        s.translatesAutoresizingMaskIntoConstraints = false
        s.axis = .vertical
        s.alignment = .center
        s.spacing = 0
        return s
    }()

    private let logoView: UIImageView = {
        let iv = UIImageView(image: UIImage(named: "SplashLogo"))
        iv.translatesAutoresizingMaskIntoConstraints = false
        iv.contentMode = .scaleAspectFit
        iv.accessibilityLabel = "DawnChat"
        return iv
    }()

    private let headlineLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.textAlignment = .center
        label.numberOfLines = 0
        label.font = .systemFont(ofSize: 22, weight: .bold)
        label.textColor = .label
        return label
    }()

    private let statusLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.textAlignment = .center
        label.numberOfLines = 0
        label.textColor = .secondaryLabel
        label.font = .systemFont(ofSize: 14, weight: .regular)
        return label
    }()

    private let loginButton: UIButton = {
        let button = UIButton(type: .system)
        button.translatesAutoresizingMaskIntoConstraints = false
        return button
    }()

    private var authSession: ASWebAuthenticationSession?
    private var authCallbackObserver: NSObjectProtocol?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        navigationItem.largeTitleDisplayMode = .never
        applyLocalizedStrings()
        layoutViews()
        loginButton.addTarget(self, action: #selector(startLogin), for: .touchUpInside)
        authCallbackObserver = NotificationCenter.default.addObserver(
            forName: .dawnchatAuthCallbackURL,
            object: nil,
            queue: .main
        ) { [weak self] note in
            guard let url = note.object as? URL else { return }
            self?.handleIncomingCallback(url: url)
        }
    }

    private func applyLocalizedStrings() {
        title = L10n.text("auth.native.title")
        headlineLabel.text = L10n.text("auth.native.title")
        statusLabel.text = L10n.text("auth.native.subtitle")
        var cfg = UIButton.Configuration.filled()
        cfg.title = L10n.text("auth.open_browser")
        cfg.cornerStyle = .large
        cfg.buttonSize = .large
        loginButton.configuration = cfg
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        Task { @MainActor in
            if await MobileAuthRepository.shared.awaitSessionVerifiedForLaunch() {
                goToMain()
            }
        }
    }

    deinit {
        if let authCallbackObserver {
            NotificationCenter.default.removeObserver(authCallbackObserver)
        }
    }

    private func layoutViews() {
        view.addSubview(scrollView)
        scrollView.addSubview(contentStack)

        contentStack.addArrangedSubview(logoView)
        contentStack.setCustomSpacing(20, after: logoView)
        contentStack.addArrangedSubview(headlineLabel)
        contentStack.setCustomSpacing(12, after: headlineLabel)
        contentStack.addArrangedSubview(statusLabel)
        contentStack.setCustomSpacing(28, after: statusLabel)
        contentStack.addArrangedSubview(loginButton)

        logoView.widthAnchor.constraint(equalToConstant: 140).isActive = true
        logoView.heightAnchor.constraint(equalToConstant: 140).isActive = true

        loginButton.widthAnchor.constraint(equalTo: contentStack.widthAnchor).isActive = true

        headlineLabel.leadingAnchor.constraint(equalTo: contentStack.leadingAnchor).isActive = true
        headlineLabel.trailingAnchor.constraint(equalTo: contentStack.trailingAnchor).isActive = true
        statusLabel.leadingAnchor.constraint(equalTo: contentStack.leadingAnchor).isActive = true
        statusLabel.trailingAnchor.constraint(equalTo: contentStack.trailingAnchor).isActive = true

        let safe = view.safeAreaLayoutGuide
        NSLayoutConstraint.activate([
            scrollView.topAnchor.constraint(equalTo: safe.topAnchor),
            scrollView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.bottomAnchor),

            contentStack.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor, constant: 28),
            contentStack.leadingAnchor.constraint(equalTo: scrollView.frameLayoutGuide.leadingAnchor, constant: 24),
            contentStack.trailingAnchor.constraint(equalTo: scrollView.frameLayoutGuide.trailingAnchor, constant: -24),
            contentStack.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor, constant: -32),
            contentStack.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor, constant: -48),
        ])
    }

    @objc private func startLogin() {
        let repo = MobileAuthRepository.shared
        guard repo.isConfigReady else {
            statusLabel.text = L10n.text("auth.config_missing")
            return
        }
        let bridgeURL: URL
        do {
            bridgeURL = try repo.prepareBridgeLogin()
        } catch {
            statusLabel.text = error.localizedDescription
            return
        }
        statusLabel.text = L10n.text("auth.waiting_return")
        let scheme = URL(string: repo.redirectURI)?.scheme ?? "com.dawnchat.app"
        authSession = ASWebAuthenticationSession(
            url: bridgeURL,
            callbackURLScheme: scheme,
            completionHandler: { [weak self] callbackURL, error in
                DispatchQueue.main.async {
                    guard let self else { return }
                    self.authSession = nil
                    if let error {
                        self.statusLabel.text = error.localizedDescription
                        return
                    }
                    guard let callbackURL else {
                        self.statusLabel.text = L10n.text("auth.cancelled")
                        return
                    }
                    Task { @MainActor in
                        await self.finishLogin(callbackURL: callbackURL)
                    }
                }
            }
        )
        authSession?.presentationContextProvider = self
        authSession?.prefersEphemeralWebBrowserSession = false
        guard let session = authSession else {
            statusLabel.text = L10n.text("auth.session_start_failed")
            return
        }
        if !session.start() {
            statusLabel.text = L10n.text("auth.session_start_failed")
        }
    }

    private func finishLogin(callbackURL: URL) async {
        do {
            try await MobileAuthRepository.shared.completeAuth(fromCallback: callbackURL)
            goToMain()
        } catch {
            statusLabel.text = error.localizedDescription
        }
    }

    private func goToMain() {
        guard let window = UIApplication.shared.connectedScenes
            .compactMap({ $0 as? UIWindowScene })
            .flatMap(\.windows)
            .first(where: { $0.isKeyWindow }) else { return }
        let root = RootTabBarController()
        UIView.transition(with: window, duration: 0.25, options: .transitionCrossDissolve) {
            window.rootViewController = root
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        if let w = view.window { return w }
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.flatMap(\.windows).first { $0.isKeyWindow }
            ?? scenes.flatMap(\.windows).first
            ?? UIWindow()
    }

    /// Cold-start / external open (e.g. full Safari): same native exchange path.
    func handleIncomingCallback(url: URL) {
        Task { @MainActor in
            do {
                try await MobileAuthRepository.shared.completeAuth(fromCallback: url)
                self.goToMain()
            } catch {
                self.statusLabel.text = error.localizedDescription
            }
        }
    }
}
