import pytest

from app.plugins.application.iwp_workspace_application_service import PluginIwpWorkspaceApplicationService


def _create_service(plugin_root):
    return PluginIwpWorkspaceApplicationService(get_plugin_path=lambda _: str(plugin_root))


def test_list_and_read_markdown_files(tmp_path) -> None:
    plugin_root = tmp_path / "plugin"
    iwp_root = plugin_root / "InstructWare.iw"
    (iwp_root / "views" / "pages").mkdir(parents=True, exist_ok=True)
    (plugin_root / ".iwp-lint.yaml").write_text("profile: test", encoding="utf-8")
    (iwp_root / "README.md").write_text("# hello", encoding="utf-8")
    (iwp_root / "views" / "pages" / "home.md").write_text("home", encoding="utf-8")

    service = _create_service(plugin_root)
    payload = service.list_markdown_files("com.demo")
    paths = [item["path"] for item in payload["files"]]

    assert payload["iwp_root"] == "InstructWare.iw"
    assert paths == ["README.md", "views/pages/home.md"]

    read_payload = service.read_markdown_file("com.demo", "views/pages/home.md")
    assert read_payload["path"] == "views/pages/home.md"
    assert read_payload["content"] == "home"
    assert isinstance(read_payload["content_hash"], str)


def test_save_markdown_file_detects_hash_conflict(tmp_path) -> None:
    plugin_root = tmp_path / "plugin"
    iwp_root = plugin_root / "InstructWare.iw"
    iwp_root.mkdir(parents=True, exist_ok=True)
    (plugin_root / ".iwp-lint.yaml").write_text("profile: test", encoding="utf-8")
    markdown_file = iwp_root / "README.md"
    markdown_file.write_text("v1", encoding="utf-8")

    service = _create_service(plugin_root)
    first = service.read_markdown_file("com.demo", "README.md")
    markdown_file.write_text("v2", encoding="utf-8")

    with pytest.raises(RuntimeError):
        service.save_markdown_file(
            "com.demo",
            "README.md",
            "v3",
            expected_hash=first["content_hash"],
        )
