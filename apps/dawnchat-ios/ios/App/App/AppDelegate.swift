import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        self.window = UIWindow(frame: UIScreen.main.bounds)
        let splash = SplashViewController()
        splash.onSplashFinished = { [weak self] in
            guard let self else { return }
            Task { @MainActor in
                await MobileAuthRepository.shared.bootstrapSupabaseIfNeeded()
                await MobileAuthRepository.shared.startSupabaseAutoRefresh()
                let ok = await MobileAuthRepository.shared.awaitSessionVerifiedForLaunch()
                guard let window = self.window else { return }
                let root: UIViewController
                if ok {
                    root = RootTabBarController()
                } else {
                    root = UINavigationController(rootViewController: NativeLoginViewController())
                }
                UIView.transition(
                    with: window,
                    duration: 0.25,
                    options: .transitionCrossDissolve
                ) {
                    window.rootViewController = root
                }
            }
        }
        self.window?.rootViewController = splash
        AppSettings.shared.applyTheme(to: self.window)
        self.window?.makeKeyAndVisible()
        return true
    }

    func applicationWillResignActive(_ application: UIApplication) {
        // Sent when the application is about to move from active to inactive state. This can occur for certain types of temporary interruptions (such as an incoming phone call or SMS message) or when the user quits the application and it begins the transition to the background state.
        // Use this method to pause ongoing tasks, disable timers, and invalidate graphics rendering callbacks. Games should use this method to pause the game.
    }

    func applicationDidEnterBackground(_ application: UIApplication) {
        Task { @MainActor in
            await MobileAuthRepository.shared.stopSupabaseAutoRefresh()
        }
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        Task { @MainActor in
            await MobileAuthRepository.shared.startSupabaseAutoRefresh()
        }
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        if MobileAuthRepository.shared.matchesRedirect(url) {
            NotificationCenter.default.post(name: .dawnchatAuthCallbackURL, object: url)
            return true
        }
        return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
    }

    func application(_ application: UIApplication, continue userActivity: NSUserActivity, restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
        // Called when the app was launched with an activity, including Universal Links.
        // Feel free to add additional processing here, but if you want the App API to support
        // tracking app url opens, make sure to keep this call
        return ApplicationDelegateProxy.shared.application(application, continue: userActivity, restorationHandler: restorationHandler)
    }

}

enum AppLanguage: String, CaseIterable {
    case system
    case zhHans
    case en

    var displayName: String {
        switch self {
        case .system:
            return "System"
        case .zhHans:
            return "简体中文"
        case .en:
            return "English"
        }
    }
}

enum AppTheme: String, CaseIterable {
    case system
    case light
    case dark

    var displayName: String {
        switch self {
        case .system:
            return "跟随系统"
        case .light:
            return "浅色"
        case .dark:
            return "深色"
        }
    }

    var interfaceStyle: UIUserInterfaceStyle {
        switch self {
        case .system:
            return .unspecified
        case .light:
            return .light
        case .dark:
            return .dark
        }
    }
}

final class AppSettings {
    static let shared = AppSettings()

    private let defaults = UserDefaults.standard
    private let languageKey = "dawnchat.mobile.language"
    private let themeKey = "dawnchat.mobile.theme"

    private init() {}

    var language: AppLanguage {
        get { AppLanguage(rawValue: defaults.string(forKey: languageKey) ?? "") ?? .system }
        set { defaults.set(newValue.rawValue, forKey: languageKey) }
    }

    var theme: AppTheme {
        get { AppTheme(rawValue: defaults.string(forKey: themeKey) ?? "") ?? .system }
        set { defaults.set(newValue.rawValue, forKey: themeKey) }
    }

    func applyTheme(to window: UIWindow?) {
        window?.overrideUserInterfaceStyle = theme.interfaceStyle
    }
}

enum L10n {
    static func text(_ key: String) -> String {
        let language = AppSettings.shared.language
        if language == .system {
            return systemText(key)
        }
        return language == .zhHans ? zh[key, default: key] : en[key, default: key]
    }

    private static func systemText(_ key: String) -> String {
        let preferred = Locale.preferredLanguages.first ?? "en"
        if preferred.lowercased().hasPrefix("zh") {
            return zh[key, default: key]
        }
        return en[key, default: key]
    }

    private static let zh: [String: String] = [
        "tab.home": "首页",
        "tab.mine": "我的",
        "mine.title": "我的",
        "mine.profile": "个人资料",
        "mine.settings": "设置",
        "mine.about": "关于",
        "mine.logout": "退出登录",
        "mine.user_fallback": "用户",
        "mine.avatar_accessibility": "用户头像",
        "auth.native.title": "登录 DawnChat",
        "auth.native.subtitle": "使用官网账号登录（系统浏览器）",
        "auth.open_browser": "打开浏览器登录",
        "auth.waiting_return": "请在浏览器中完成登录…",
        "auth.config_missing": "请在 Info.plist 填写 DawnChatSupabaseURL 与 DawnChatSupabaseAnonKey",
        "auth.cancelled": "登录已取消",
        "auth.session_start_failed": "无法启动登录会话",
        "profile.title": "个人资料",
        "profile.field.email": "邮箱",
        "profile.field.user_id": "用户 ID",
        "profile.field.phone": "手机号",
        "profile.field.display_name": "显示名称",
        "profile.field.created_at": "注册时间",
        "profile.field.last_sign_in": "上次登录",
        "profile.empty": "—",
        "settings.title": "设置",
        "settings.language": "语言",
        "settings.theme": "主题",
        "settings.mobile_assistant": "Mobile AI 助手",
        "settings.auto_open_mobile_assistant": "进入首页时自动打开内置助手",
        "settings.tip": "语言切换建议重启 App 以保证全部页面一致。",
        "about.title": "关于",
        "about.summary": "DawnChat Mobile Dev Host",
        "about.desc": "用于加载 HMR 与离线 Capacitor 插件产物的开发宿主。",
        "common.system": "跟随系统",
        "common.ok": "确定",
        "splash.app_name": "DawnChat",
        "splash.app_subtitle": "构建可持续进化的 App。"
    ]

    private static let en: [String: String] = [
        "tab.home": "Home",
        "tab.mine": "Mine",
        "mine.title": "Mine",
        "mine.profile": "Profile",
        "mine.settings": "Settings",
        "mine.about": "About",
        "mine.logout": "Log out",
        "mine.user_fallback": "User",
        "mine.avatar_accessibility": "Profile picture",
        "auth.native.title": "Sign in to DawnChat",
        "auth.native.subtitle": "Use your DawnChat account (system browser)",
        "auth.open_browser": "Open browser to sign in",
        "auth.waiting_return": "Complete sign-in in the browser…",
        "auth.config_missing": "Set DawnChatSupabaseURL and DawnChatSupabaseAnonKey in Info.plist",
        "auth.cancelled": "Sign-in cancelled",
        "auth.session_start_failed": "Could not start sign-in session",
        "profile.title": "Profile",
        "profile.field.email": "Email",
        "profile.field.user_id": "User ID",
        "profile.field.phone": "Phone",
        "profile.field.display_name": "Display name",
        "profile.field.created_at": "Created at",
        "profile.field.last_sign_in": "Last sign-in",
        "profile.empty": "—",
        "settings.title": "Settings",
        "settings.language": "Language",
        "settings.theme": "Theme",
        "settings.mobile_assistant": "Mobile AI assistant",
        "settings.auto_open_mobile_assistant": "Open built-in assistant when Home appears",
        "settings.tip": "Restart the app to apply language changes everywhere.",
        "about.title": "About",
        "about.summary": "DawnChat Mobile Dev Host",
        "about.desc": "Developer host for loading HMR and offline Capacitor bundles.",
        "common.system": "System",
        "common.ok": "OK",
        "splash.app_name": "DawnChat",
        "splash.app_subtitle": "DawnChat is built for apps that keep evolving."
    ]
}

final class SplashViewController: UIViewController {
    var onSplashFinished: (() -> Void)?

    private let logoView: UIImageView = {
        let iv = UIImageView(image: UIImage(named: "SplashLogo"))
        iv.translatesAutoresizingMaskIntoConstraints = false
        iv.contentMode = .scaleAspectFit
        iv.accessibilityLabel = "DawnChat"
        return iv
    }()

    private let appNameLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.font = .systemFont(ofSize: 22, weight: .bold)
        label.textAlignment = .center
        label.textColor = UIColor(red: 0.067, green: 0.094, blue: 0.153, alpha: 1)
        return label
    }()

    private let sloganLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.font = .systemFont(ofSize: 14, weight: .regular)
        label.textAlignment = .center
        label.textColor = UIColor(red: 0.420, green: 0.451, blue: 0.502, alpha: 1)
        label.numberOfLines = 0
        return label
    }()

    private let indicator: UIActivityIndicatorView = {
        let view = UIActivityIndicatorView(style: .medium)
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .white
        appNameLabel.text = L10n.text("splash.app_name")
        sloganLabel.text = L10n.text("splash.app_subtitle")
        layoutViews()
        indicator.startAnimating()
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { [weak self] in
            self?.onSplashFinished?()
        }
    }

    private func layoutViews() {
        let safe = view.safeAreaLayoutGuide
        let stack = UIStackView(arrangedSubviews: [logoView, appNameLabel, sloganLabel])
        stack.translatesAutoresizingMaskIntoConstraints = false
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 0
        stack.setCustomSpacing(16, after: logoView)
        stack.setCustomSpacing(10, after: appNameLabel)

        view.addSubview(stack)
        view.addSubview(indicator)

        NSLayoutConstraint.activate([
            logoView.widthAnchor.constraint(equalToConstant: 180),
            logoView.heightAnchor.constraint(equalToConstant: 180),
            logoView.centerXAnchor.constraint(equalTo: stack.centerXAnchor),

            // 整组水平铺满安全区内边距，垂直方向居中并略偏下
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor, constant: 40),
            stack.widthAnchor.constraint(equalTo: safe.widthAnchor, constant: -80),
            sloganLabel.widthAnchor.constraint(equalTo: stack.widthAnchor),

            indicator.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            indicator.topAnchor.constraint(equalTo: stack.bottomAnchor, constant: 28),
            indicator.bottomAnchor.constraint(lessThanOrEqualTo: safe.bottomAnchor, constant: -24)
        ])
    }
}

final class RootTabBarController: UITabBarController {
    override func viewDidLoad() {
        super.viewDidLoad()

        let home = UINavigationController(rootViewController: LobbyViewController())
        home.tabBarItem = UITabBarItem(
            title: L10n.text("tab.home"),
            image: UIImage(systemName: "house"),
            selectedImage: UIImage(systemName: "house.fill")
        )

        let mine = UINavigationController(rootViewController: MineViewController())
        mine.tabBarItem = UITabBarItem(
            title: L10n.text("tab.mine"),
            image: UIImage(systemName: "person"),
            selectedImage: UIImage(systemName: "person.fill")
        )

        viewControllers = [home, mine]
    }
}

final class MineViewController: UITableViewController {

    private enum Item: Int, CaseIterable {
        case profile
        case settings
        case about
        case logout
    }

    private let mineHeaderContainer = UIView()
    private let avatarView: UIImageView = {
        let iv = UIImageView()
        iv.translatesAutoresizingMaskIntoConstraints = false
        iv.contentMode = .scaleAspectFill
        iv.clipsToBounds = true
        iv.layer.cornerRadius = 28
        iv.backgroundColor = .secondarySystemFill
        iv.image = UIImage(systemName: "person.fill")
        iv.tintColor = .secondaryLabel
        return iv
    }()

    private let primaryLabel: UILabel = {
        let l = UILabel()
        l.translatesAutoresizingMaskIntoConstraints = false
        l.font = .systemFont(ofSize: 17, weight: .semibold)
        l.numberOfLines = 2
        return l
    }()

    private let secondaryLabel: UILabel = {
        let l = UILabel()
        l.translatesAutoresizingMaskIntoConstraints = false
        l.font = .preferredFont(forTextStyle: .subheadline)
        l.textColor = .secondaryLabel
        l.numberOfLines = 2
        return l
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = L10n.text("mine.title")
        tableView = UITableView(frame: .zero, style: .insetGrouped)
        layoutMineHeader()
        avatarView.accessibilityLabel = L10n.text("mine.avatar_accessibility")
        tableView.tableHeaderView = mineHeaderContainer
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        Task { @MainActor in
            let snap = await MobileAuthRepository.shared.loadProfileForUi()
            applyProfile(snap)
        }
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        guard let header = tableView.tableHeaderView else { return }
        let width = tableView.bounds.width
        guard width > 0 else { return }
        let size = header.systemLayoutSizeFitting(
            CGSize(width: width, height: 0),
            withHorizontalFittingPriority: .required,
            verticalFittingPriority: .fittingSizeLevel
        )
        if abs(header.frame.height - size.height) > 0.5 || abs(header.frame.width - width) > 0.5 {
            header.frame = CGRect(x: 0, y: 0, width: width, height: size.height)
            tableView.tableHeaderView = header
        }
    }

    private func layoutMineHeader() {
        mineHeaderContainer.translatesAutoresizingMaskIntoConstraints = false
        mineHeaderContainer.addSubview(avatarView)
        mineHeaderContainer.addSubview(primaryLabel)
        mineHeaderContainer.addSubview(secondaryLabel)
        NSLayoutConstraint.activate([
            avatarView.leadingAnchor.constraint(equalTo: mineHeaderContainer.leadingAnchor, constant: 20),
            avatarView.topAnchor.constraint(equalTo: mineHeaderContainer.topAnchor, constant: 12),
            avatarView.widthAnchor.constraint(equalToConstant: 56),
            avatarView.heightAnchor.constraint(equalToConstant: 56),
            avatarView.bottomAnchor.constraint(equalTo: mineHeaderContainer.bottomAnchor, constant: -12),

            primaryLabel.leadingAnchor.constraint(equalTo: avatarView.trailingAnchor, constant: 14),
            primaryLabel.trailingAnchor.constraint(equalTo: mineHeaderContainer.trailingAnchor, constant: -20),
            primaryLabel.topAnchor.constraint(equalTo: avatarView.topAnchor, constant: 2),

            secondaryLabel.leadingAnchor.constraint(equalTo: primaryLabel.leadingAnchor),
            secondaryLabel.trailingAnchor.constraint(equalTo: primaryLabel.trailingAnchor),
            secondaryLabel.topAnchor.constraint(equalTo: primaryLabel.bottomAnchor, constant: 4),
        ])
    }

    private func applyProfile(_ snap: UserProfileSnapshot?) {
        if snap == nil {
            primaryLabel.text = L10n.text("mine.user_fallback")
            secondaryLabel.text = ""
            avatarView.image = UIImage(systemName: "person.fill")
            avatarView.tintColor = .secondaryLabel
            return
        }
        let s = snap!
        let display = s.displayName.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? ""
        let email = s.email.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? ""
        let primary = !display.isEmpty ? display : (!email.isEmpty ? email : L10n.text("mine.user_fallback"))
        primaryLabel.text = primary
        let sec = !email.isEmpty ? email : String(s.id.prefix(12)) + "…"
        secondaryLabel.text = sec
        let rawAvatar = s.avatarUrl.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) } ?? ""
        if !rawAvatar.isEmpty, let url = URL(string: rawAvatar) {
            Task {
                await loadAvatar(from: url)
            }
        } else {
            avatarView.image = UIImage(systemName: "person.fill")
            avatarView.tintColor = .secondaryLabel
        }
    }

    private func loadAvatar(from url: URL) async {
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let img = UIImage(data: data) else { return }
            await MainActor.run {
                self.avatarView.tintColor = nil
                self.avatarView.image = img
            }
        } catch {
            await MainActor.run {
                self.avatarView.image = UIImage(systemName: "person.fill")
                self.avatarView.tintColor = .secondaryLabel
            }
        }
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        Item.allCases.count
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.accessoryType = .disclosureIndicator
        switch Item(rawValue: indexPath.row) {
        case .profile:
            cell.textLabel?.text = L10n.text("mine.profile")
            cell.imageView?.image = UIImage(systemName: "person.crop.circle")
        case .settings:
            cell.textLabel?.text = L10n.text("mine.settings")
            cell.imageView?.image = UIImage(systemName: "gearshape")
        case .about:
            cell.textLabel?.text = L10n.text("mine.about")
            cell.imageView?.image = UIImage(systemName: "info.circle")
        case .logout:
            cell.textLabel?.text = L10n.text("mine.logout")
            cell.imageView?.image = UIImage(systemName: "rectangle.portrait.and.arrow.right")
        case .none:
            break
        }
        return cell
    }

    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        switch Item(rawValue: indexPath.row) {
        case .profile:
            navigationController?.pushViewController(ProfileViewController(), animated: true)
        case .settings:
            navigationController?.pushViewController(SettingsViewController(), animated: true)
        case .about:
            navigationController?.pushViewController(AboutViewController(), animated: true)
        case .logout:
            Task { @MainActor in
                await MobileAuthRepository.shared.clearSession()
                guard let window = UIApplication.shared.connectedScenes
                    .compactMap({ $0 as? UIWindowScene })
                    .flatMap(\.windows)
                    .first(where: { $0.isKeyWindow }) else { return }
                window.rootViewController = UINavigationController(rootViewController: NativeLoginViewController())
            }
        case .none:
            break
        }
    }
}

final class SettingsViewController: UITableViewController {
    private let languageControl = UISegmentedControl(items: AppLanguage.allCases.map { $0.displayName })
    private let themeControl = UISegmentedControl(items: AppTheme.allCases.map { $0.displayName })
    private let autoOpenAssistantSwitch = UISwitch()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = L10n.text("settings.title")
        tableView = UITableView(frame: .zero, style: .insetGrouped)
        configureControls()
    }

    private func configureControls() {
        languageControl.selectedSegmentIndex = AppLanguage.allCases.firstIndex(of: AppSettings.shared.language) ?? 0
        themeControl.selectedSegmentIndex = AppTheme.allCases.firstIndex(of: AppSettings.shared.theme) ?? 0
        autoOpenAssistantSwitch.isOn = HostBuiltinAssistantPrefs.isAutoOpenEnabled

        languageControl.addTarget(self, action: #selector(languageChanged), for: .valueChanged)
        themeControl.addTarget(self, action: #selector(themeChanged), for: .valueChanged)
        autoOpenAssistantSwitch.addTarget(self, action: #selector(autoOpenAssistantChanged), for: .valueChanged)
    }

    @objc private func languageChanged() {
        guard AppLanguage.allCases.indices.contains(languageControl.selectedSegmentIndex) else { return }
        AppSettings.shared.language = AppLanguage.allCases[languageControl.selectedSegmentIndex]
        let alert = UIAlertController(
            title: nil,
            message: L10n.text("settings.tip"),
            preferredStyle: .alert
        )
        alert.addAction(UIAlertAction(title: L10n.text("common.ok"), style: .default))
        present(alert, animated: true)
    }

    @objc private func themeChanged() {
        guard AppTheme.allCases.indices.contains(themeControl.selectedSegmentIndex) else { return }
        AppSettings.shared.theme = AppTheme.allCases[themeControl.selectedSegmentIndex]
        if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
            scene.windows.first?.overrideUserInterfaceStyle = AppSettings.shared.theme.interfaceStyle
        }
    }

    @objc private func autoOpenAssistantChanged() {
        HostBuiltinAssistantPrefs.setAutoOpenEnabled(autoOpenAssistantSwitch.isOn)
    }

    override func numberOfSections(in tableView: UITableView) -> Int {
        3
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        1
    }

    override func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        switch section {
        case 0: return L10n.text("settings.language")
        case 1: return L10n.text("settings.theme")
        case 2: return L10n.text("settings.mobile_assistant")
        default: return nil
        }
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.selectionStyle = .none
        switch indexPath.section {
        case 0, 1:
            let control = indexPath.section == 0 ? languageControl : themeControl
            control.translatesAutoresizingMaskIntoConstraints = false
            cell.contentView.addSubview(control)
            NSLayoutConstraint.activate([
                control.leadingAnchor.constraint(equalTo: cell.contentView.leadingAnchor, constant: 16),
                control.trailingAnchor.constraint(equalTo: cell.contentView.trailingAnchor, constant: -16),
                control.topAnchor.constraint(equalTo: cell.contentView.topAnchor, constant: 10),
                control.bottomAnchor.constraint(equalTo: cell.contentView.bottomAnchor, constant: -10)
            ])
        default:
            cell.textLabel?.text = L10n.text("settings.auto_open_mobile_assistant")
            cell.textLabel?.numberOfLines = 0
            autoOpenAssistantSwitch.translatesAutoresizingMaskIntoConstraints = false
            cell.accessoryView = autoOpenAssistantSwitch
        }
        return cell
    }
}

final class AboutViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = L10n.text("about.title")
        setupContent()
    }

    private func setupContent() {
        let stack = UIStackView()
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false

        let titleLabel = UILabel()
        titleLabel.text = L10n.text("about.summary")
        titleLabel.font = .systemFont(ofSize: 24, weight: .bold)

        let versionLabel = UILabel()
        versionLabel.text = "v\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")"
        versionLabel.textColor = .secondaryLabel

        let desc = UILabel()
        desc.text = L10n.text("about.desc")
        desc.textColor = .secondaryLabel
        desc.numberOfLines = 0
        desc.textAlignment = .center

        stack.addArrangedSubview(titleLabel)
        stack.addArrangedSubview(versionLabel)
        stack.addArrangedSubview(desc)

        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }
}
