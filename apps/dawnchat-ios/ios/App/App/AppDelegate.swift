import UIKit
import Capacitor

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        self.window = UIWindow(frame: UIScreen.main.bounds)
        let splash = SplashViewController()
        splash.onSplashFinished = { [weak self] in
            guard let self, let window = self.window else { return }
            let root = RootTabBarController()
            UIView.transition(
                with: window,
                duration: 0.25,
                options: .transitionCrossDissolve
            ) {
                window.rootViewController = root
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
        // Use this method to release shared resources, save user data, invalidate timers, and store enough application state information to restore your application to its current state in case it is terminated later.
        // If your application supports background execution, this method is called instead of applicationWillTerminate: when the user quits.
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        // Called as part of the transition from the background to the active state; here you can undo many of the changes made on entering the background.
    }

    func applicationDidBecomeActive(_ application: UIApplication) {
        // Restart any tasks that were paused (or not yet started) while the application was inactive. If the application was previously in the background, optionally refresh the user interface.
    }

    func applicationWillTerminate(_ application: UIApplication) {
        // Called when the application is about to terminate. Save data if appropriate. See also applicationDidEnterBackground:.
    }

    func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey: Any] = [:]) -> Bool {
        // Called when the app was launched with a url. Feel free to add additional processing here,
        // but if you want the App API to support tracking app url opens, make sure to keep this call
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
        "mine.settings": "设置",
        "mine.about": "关于",
        "settings.title": "设置",
        "settings.language": "语言",
        "settings.theme": "主题",
        "settings.tip": "语言切换建议重启 App 以保证全部页面一致。",
        "about.title": "关于",
        "about.summary": "DawnChat Mobile Dev Host",
        "about.desc": "用于加载 HMR 与离线 Capacitor 插件产物的开发宿主。",
        "common.system": "跟随系统",
        "common.ok": "确定"
    ]

    private static let en: [String: String] = [
        "tab.home": "Home",
        "tab.mine": "Mine",
        "mine.title": "Mine",
        "mine.settings": "Settings",
        "mine.about": "About",
        "settings.title": "Settings",
        "settings.language": "Language",
        "settings.theme": "Theme",
        "settings.tip": "Restart the app to apply language changes everywhere.",
        "about.title": "About",
        "about.summary": "DawnChat Mobile Dev Host",
        "about.desc": "Developer host for loading HMR and offline Capacitor bundles.",
        "common.system": "System",
        "common.ok": "OK"
    ]
}

final class SplashViewController: UIViewController {
    var onSplashFinished: (() -> Void)?

    private let logoLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.text = "DawnChat"
        label.font = .systemFont(ofSize: 36, weight: .bold)
        return label
    }()

    private let subtitleLabel: UILabel = {
        let label = UILabel()
        label.translatesAutoresizingMaskIntoConstraints = false
        label.text = "Mobile Dev Host"
        label.font = .systemFont(ofSize: 16, weight: .medium)
        label.textColor = .secondaryLabel
        return label
    }()

    private let indicator: UIActivityIndicatorView = {
        let view = UIActivityIndicatorView(style: .medium)
        view.translatesAutoresizingMaskIntoConstraints = false
        return view
    }()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
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
        view.addSubview(logoLabel)
        view.addSubview(subtitleLabel)
        view.addSubview(indicator)

        NSLayoutConstraint.activate([
            logoLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            logoLabel.centerYAnchor.constraint(equalTo: view.centerYAnchor, constant: -18),
            subtitleLabel.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            subtitleLabel.topAnchor.constraint(equalTo: logoLabel.bottomAnchor, constant: 8),
            indicator.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            indicator.topAnchor.constraint(equalTo: subtitleLabel.bottomAnchor, constant: 20)
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
        case settings
        case about
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = L10n.text("mine.title")
        tableView = UITableView(frame: .zero, style: .insetGrouped)
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        Item.allCases.count
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.accessoryType = .disclosureIndicator
        switch Item(rawValue: indexPath.row) {
        case .settings:
            cell.textLabel?.text = L10n.text("mine.settings")
            cell.imageView?.image = UIImage(systemName: "gearshape")
        case .about:
            cell.textLabel?.text = L10n.text("mine.about")
            cell.imageView?.image = UIImage(systemName: "info.circle")
        case .none:
            break
        }
        return cell
    }

    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        switch Item(rawValue: indexPath.row) {
        case .settings:
            navigationController?.pushViewController(SettingsViewController(), animated: true)
        case .about:
            navigationController?.pushViewController(AboutViewController(), animated: true)
        case .none:
            break
        }
    }
}

final class SettingsViewController: UITableViewController {
    private let languageControl = UISegmentedControl(items: AppLanguage.allCases.map { $0.displayName })
    private let themeControl = UISegmentedControl(items: AppTheme.allCases.map { $0.displayName })

    override func viewDidLoad() {
        super.viewDidLoad()
        title = L10n.text("settings.title")
        tableView = UITableView(frame: .zero, style: .insetGrouped)
        configureControls()
    }

    private func configureControls() {
        languageControl.selectedSegmentIndex = AppLanguage.allCases.firstIndex(of: AppSettings.shared.language) ?? 0
        themeControl.selectedSegmentIndex = AppTheme.allCases.firstIndex(of: AppSettings.shared.theme) ?? 0

        languageControl.addTarget(self, action: #selector(languageChanged), for: .valueChanged)
        themeControl.addTarget(self, action: #selector(themeChanged), for: .valueChanged)
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

    override func numberOfSections(in tableView: UITableView) -> Int {
        2
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        1
    }

    override func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        section == 0 ? L10n.text("settings.language") : L10n.text("settings.theme")
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
        cell.selectionStyle = .none
        let control = indexPath.section == 0 ? languageControl : themeControl
        control.translatesAutoresizingMaskIntoConstraints = false
        cell.contentView.addSubview(control)
        NSLayoutConstraint.activate([
            control.leadingAnchor.constraint(equalTo: cell.contentView.leadingAnchor, constant: 16),
            control.trailingAnchor.constraint(equalTo: cell.contentView.trailingAnchor, constant: -16),
            control.topAnchor.constraint(equalTo: cell.contentView.topAnchor, constant: 10),
            control.bottomAnchor.constraint(equalTo: cell.contentView.bottomAnchor, constant: -10)
        ])
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
