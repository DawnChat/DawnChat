import UIKit

/// Read-only Supabase Auth profile fields (same snapshot as Android).
final class ProfileViewController: UITableViewController {

    private var rows: [(title: String, value: String)] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        title = L10n.text("profile.title")
        tableView = UITableView(frame: .zero, style: .insetGrouped)
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "profileCell")
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        Task { @MainActor in
            let snap = await MobileAuthRepository.shared.loadProfileForUi()
            rows = Self.buildRows(from: snap)
            tableView.reloadData()
        }
    }

    private static func buildRows(from s: UserProfileSnapshot?) -> [(String, String)] {
        let empty = L10n.text("profile.empty")
        guard let s else {
            return [
                (L10n.text("profile.field.email"), empty),
                (L10n.text("profile.field.user_id"), empty),
                (L10n.text("profile.field.display_name"), empty),
                (L10n.text("profile.field.created_at"), empty),
                (L10n.text("profile.field.last_sign_in"), empty),
            ]
        }
        func nonempty(_ v: String?) -> String {
            let t = v?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return t.isEmpty ? empty : t
        }
        var r: [(String, String)] = [
            (L10n.text("profile.field.email"), nonempty(s.email)),
            (L10n.text("profile.field.user_id"), nonempty(s.id)),
        ]
        if let p = s.phone, !p.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            r.append((L10n.text("profile.field.phone"), p))
        }
        r.append((L10n.text("profile.field.display_name"), nonempty(s.displayName)))
        r.append((L10n.text("profile.field.created_at"), nonempty(s.createdAtIso)))
        r.append((L10n.text("profile.field.last_sign_in"), nonempty(s.lastSignInAtIso)))
        return r
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        rows.count
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "profileCell", for: indexPath)
        cell.selectionStyle = .none
        let row = rows[indexPath.row]
        var config = UIListContentConfiguration.valueCell()
        config.text = row.title
        config.secondaryText = row.value
        config.textProperties.font = .preferredFont(forTextStyle: .subheadline)
        config.textProperties.color = .secondaryLabel
        config.secondaryTextProperties.font = .preferredFont(forTextStyle: .body)
        config.secondaryTextProperties.numberOfLines = 0
        cell.contentConfiguration = config
        return cell
    }
}
