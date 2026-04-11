import json

import pytest

from app.plugins.scaffolding.base import TemplateScaffoldRequest
from app.plugins.scaffolding.desktop_scaffolder import DesktopTemplateScaffolder
from app.plugins.scaffolding.web_scaffolder import WebTemplateScaffolder


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _create_sdk_package(path, name: str, *, package_json: dict | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    payload = package_json or {
            "name": name,
            "version": "0.1.0",
            "main": "./dist/index.js",
            "types": "./dist/index.d.ts",
            "exports": {
                ".": {
                    "types": "./dist/index.d.ts",
                    "import": "./dist/index.js",
                }
            },
        }
    _write_json(path / "package.json", payload)
    dist_dir = path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    (dist_dir / "index.js").write_text("export {};\n", encoding="utf-8")
    (dist_dir / "index.d.ts").write_text("export {};\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_desktop_scaffolder_rewrites_assistant_sdk_to_sidecar_file_dependency(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_source = tmp_path / "desktop-template"
    target_dir = tmp_path / "com.demo.assistant"
    assistant_core_dir = tmp_path / "sidecar" / "assistant-sdk" / "assistant-core"
    _create_sdk_package(assistant_core_dir, "@dawnchat/assistant-core")

    _write_json(
        template_source / "manifest.json",
        {
            "id": "com.template.assistant",
            "name": "Assistant Template",
            "description": "template",
            "author": "template@example.com",
        },
    )
    _write_json(
        template_source / "_ir" / "frontend" / "web-src" / "package.json",
        {
            "name": "desktop-template",
            "version": "0.1.0",
            "dependencies": {
                "@dawnchat/assistant-core": "workspace:*",
                "vue": "^3.5.0",
            },
        },
    )

    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_runtime_distribution_mode",
        lambda: "dev",
    )
    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_assistant_sdk_package_dirs",
        lambda allow_dev_fallback=False: {
            "@dawnchat/assistant-core": assistant_core_dir,
            "@dawnchat/host-orchestration-sdk": tmp_path / "missing-host-sdk",
        },
    )

    await DesktopTemplateScaffolder().scaffold(
        TemplateScaffoldRequest(
            template_id="com.template.assistant",
            app_type="desktop",
            plugin_id="com.demo.assistant",
            app_name="Demo Assistant",
            app_description="demo",
            owner_email="demo@example.com",
            owner_user_id="u1",
            template_source=template_source,
            target_dir=target_dir,
        )
    )

    package_json = json.loads(
        (target_dir / "_ir" / "frontend" / "web-src" / "package.json").read_text(encoding="utf-8")
    )
    assert package_json["dependencies"]["@dawnchat/assistant-core"] == f"file:{assistant_core_dir.resolve().as_posix()}"


@pytest.mark.asyncio
async def test_web_scaffolder_vendors_assistant_sdk_for_release_runtime(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_source = tmp_path / "web-template"
    target_dir = tmp_path / "com.demo.web"
    assistant_app_sdk_dir = tmp_path / "bundle" / "assistant-sdk" / "assistant-app-sdk"
    assistant_chat_ui_dir = tmp_path / "bundle" / "assistant-sdk" / "assistant-chat-ui"
    assistant_core_dir = tmp_path / "bundle" / "assistant-sdk" / "assistant-core"
    host_sdk_dir = tmp_path / "bundle" / "assistant-sdk" / "host-orchestration-sdk"
    _create_sdk_package(
        assistant_app_sdk_dir,
        "@dawnchat/assistant-app-sdk",
        package_json={
            "name": "@dawnchat/assistant-app-sdk",
            "version": "0.1.0",
            "main": "./dist/index.js",
            "types": "./dist/index.d.ts",
            "exports": {
                ".": {
                    "types": "./dist/index.d.ts",
                    "import": "./dist/index.js",
                }
            },
            "scripts": {
                "build": "vite build",
            },
            "peerDependencies": {
                "@dawnchat/host-orchestration-sdk": "workspace:*",
            },
            "devDependencies": {
                "@dawnchat/host-orchestration-sdk": "workspace:*",
            },
        },
    )
    _create_sdk_package(assistant_chat_ui_dir, "@dawnchat/assistant-chat-ui")
    _create_sdk_package(assistant_core_dir, "@dawnchat/assistant-core")
    _create_sdk_package(host_sdk_dir, "@dawnchat/host-orchestration-sdk")

    _write_json(
        template_source / "manifest.json",
        {
            "id": "com.template.web",
            "name": "Web Template",
            "description": "template",
            "author": "template@example.com",
        },
    )
    _write_json(
        template_source / "web-src" / "package.json",
        {
            "name": "web-template",
            "version": "0.1.0",
            "dependencies": {
                "@dawnchat/assistant-app-sdk": "workspace:*",
                "@dawnchat/assistant-chat-ui": "workspace:*",
                "@dawnchat/assistant-core": "workspace:*",
            },
        },
    )

    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_runtime_distribution_mode",
        lambda: "release",
    )
    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_assistant_sdk_package_dirs",
        lambda allow_dev_fallback=False: {
            "@dawnchat/assistant-app-sdk": assistant_app_sdk_dir,
            "@dawnchat/assistant-chat-ui": assistant_chat_ui_dir,
            "@dawnchat/assistant-core": assistant_core_dir,
            "@dawnchat/host-orchestration-sdk": host_sdk_dir,
        },
    )

    await WebTemplateScaffolder().scaffold(
        TemplateScaffoldRequest(
            template_id="com.template.web",
            app_type="web",
            plugin_id="com.demo.web",
            app_name="Demo Web",
            app_description="demo",
            owner_email="demo@example.com",
            owner_user_id="u1",
            template_source=template_source,
            target_dir=target_dir,
        )
    )

    package_json = json.loads((target_dir / "web-src" / "package.json").read_text(encoding="utf-8"))
    assert package_json["dependencies"]["@dawnchat/assistant-app-sdk"] == "file:../vendor/assistant-sdk/assistant-app-sdk"
    assert package_json["dependencies"]["@dawnchat/assistant-chat-ui"] == "file:../vendor/assistant-sdk/assistant-chat-ui"
    assert package_json["dependencies"]["@dawnchat/assistant-core"] == "file:../vendor/assistant-sdk/assistant-core"
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-app-sdk" / "package.json").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-chat-ui" / "package.json").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-core" / "package.json").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "host-orchestration-sdk" / "package.json").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-app-sdk" / "dist" / "index.js").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-chat-ui" / "dist" / "index.js").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "assistant-core" / "dist" / "index.js").exists()
    assert (target_dir / "vendor" / "assistant-sdk" / "host-orchestration-sdk" / "dist" / "index.js").exists()
    vendored_app_sdk_package_json = json.loads(
        (target_dir / "vendor" / "assistant-sdk" / "assistant-app-sdk" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    assert vendored_app_sdk_package_json["dependencies"]["@dawnchat/host-orchestration-sdk"] == "file:../host-orchestration-sdk"
    assert "devDependencies" not in vendored_app_sdk_package_json
    assert "scripts" not in vendored_app_sdk_package_json
    assert "peerDependencies" not in vendored_app_sdk_package_json


@pytest.mark.asyncio
async def test_web_scaffolder_rewrites_workspace_assistant_sdk_to_dev_file_dependency(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_source = tmp_path / "web-template"
    target_dir = tmp_path / "com.demo.web"
    assistant_app_sdk_dir = tmp_path / "sidecar" / "assistant-sdk" / "assistant-app-sdk"
    assistant_chat_ui_dir = tmp_path / "sidecar" / "assistant-sdk" / "assistant-chat-ui"
    assistant_core_dir = tmp_path / "sidecar" / "assistant-sdk" / "assistant-core"
    host_sdk_dir = tmp_path / "sidecar" / "assistant-sdk" / "host-orchestration-sdk"
    _create_sdk_package(assistant_app_sdk_dir, "@dawnchat/assistant-app-sdk")
    _create_sdk_package(assistant_chat_ui_dir, "@dawnchat/assistant-chat-ui")
    _create_sdk_package(assistant_core_dir, "@dawnchat/assistant-core")
    _create_sdk_package(host_sdk_dir, "@dawnchat/host-orchestration-sdk")

    _write_json(
        template_source / "manifest.json",
        {
            "id": "com.template.web",
            "name": "Web Template",
            "description": "template",
            "author": "template@example.com",
        },
    )
    _write_json(
        template_source / "web-src" / "package.json",
        {
            "name": "web-template",
            "version": "0.1.0",
            "dependencies": {
                "@dawnchat/assistant-app-sdk": "workspace:*",
                "@dawnchat/assistant-chat-ui": "workspace:*",
                "@dawnchat/assistant-core": "workspace:*",
                "@dawnchat/host-orchestration-sdk": "workspace:*",
            },
        },
    )

    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_runtime_distribution_mode",
        lambda: "dev",
    )
    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_assistant_sdk_package_dirs",
        lambda allow_dev_fallback=False: {
            "@dawnchat/assistant-app-sdk": assistant_app_sdk_dir,
            "@dawnchat/assistant-chat-ui": assistant_chat_ui_dir,
            "@dawnchat/assistant-core": assistant_core_dir,
            "@dawnchat/host-orchestration-sdk": host_sdk_dir,
        },
    )

    await WebTemplateScaffolder().scaffold(
        TemplateScaffoldRequest(
            template_id="com.template.web",
            app_type="web",
            plugin_id="com.demo.web",
            app_name="Demo Web",
            app_description="demo",
            owner_email="demo@example.com",
            owner_user_id="u1",
            template_source=template_source,
            target_dir=target_dir,
        )
    )

    package_json = json.loads((target_dir / "web-src" / "package.json").read_text(encoding="utf-8"))
    assert (
        package_json["dependencies"]["@dawnchat/assistant-app-sdk"]
        == f"file:{assistant_app_sdk_dir.resolve().as_posix()}"
    )
    assert (
        package_json["dependencies"]["@dawnchat/assistant-chat-ui"]
        == f"file:{assistant_chat_ui_dir.resolve().as_posix()}"
    )
    assert package_json["dependencies"]["@dawnchat/assistant-core"] == f"file:{assistant_core_dir.resolve().as_posix()}"
    assert (
        package_json["dependencies"]["@dawnchat/host-orchestration-sdk"]
        == f"file:{host_sdk_dir.resolve().as_posix()}"
    )


def test_rewrite_frontend_sdk_dependencies_accepts_legacy_repo_local_file_reference(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "project"
    assistant_sdk_root = project_root / "dawnchat-plugins" / "assistant-sdk"
    assistant_app_sdk_dir = assistant_sdk_root / "assistant-app-sdk"
    assistant_chat_ui_dir = assistant_sdk_root / "assistant-chat-ui"
    assistant_core_dir = assistant_sdk_root / "assistant-core"
    host_sdk_dir = assistant_sdk_root / "host-orchestration-sdk"
    _create_sdk_package(assistant_app_sdk_dir, "@dawnchat/assistant-app-sdk")
    _create_sdk_package(assistant_chat_ui_dir, "@dawnchat/assistant-chat-ui")
    _create_sdk_package(assistant_core_dir, "@dawnchat/assistant-core")
    _create_sdk_package(host_sdk_dir, "@dawnchat/host-orchestration-sdk")

    plugin_root = project_root / "dawnchat-plugins" / "official-plugins" / "web-ai-assistant"
    package_json_path = plugin_root / "web-src" / "package.json"
    _write_json(
        package_json_path,
        {
            "name": "web-template",
            "version": "0.1.0",
            "dependencies": {
                "@dawnchat/assistant-app-sdk": "file:../../../assistant-sdk/assistant-app-sdk",
                "@dawnchat/assistant-chat-ui": "file:../../../assistant-sdk/assistant-chat-ui",
                "@dawnchat/assistant-core": "file:../../../assistant-sdk/assistant-core",
                "@dawnchat/host-orchestration-sdk": "file:../../../assistant-sdk/host-orchestration-sdk",
            },
        },
    )

    monkeypatch.setattr("app.plugins.scaffolding.base.Config.PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_runtime_distribution_mode",
        lambda: "dev",
    )
    monkeypatch.setattr(
        "app.plugins.scaffolding.base.Config.get_assistant_sdk_package_dirs",
        lambda allow_dev_fallback=False: {
            "@dawnchat/assistant-app-sdk": assistant_app_sdk_dir,
            "@dawnchat/assistant-chat-ui": assistant_chat_ui_dir,
            "@dawnchat/assistant-core": assistant_core_dir,
            "@dawnchat/host-orchestration-sdk": host_sdk_dir,
        },
    )

    rewritten = WebTemplateScaffolder.rewrite_frontend_sdk_dependencies(
        package_json_path,
        plugin_root=plugin_root,
    )

    assert rewritten is True
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    assert (
        package_json["dependencies"]["@dawnchat/assistant-app-sdk"]
        == f"file:{assistant_app_sdk_dir.resolve().as_posix()}"
    )
    assert (
        package_json["dependencies"]["@dawnchat/assistant-chat-ui"]
        == f"file:{assistant_chat_ui_dir.resolve().as_posix()}"
    )
    assert package_json["dependencies"]["@dawnchat/assistant-core"] == f"file:{assistant_core_dir.resolve().as_posix()}"
    assert (
        package_json["dependencies"]["@dawnchat/host-orchestration-sdk"]
        == f"file:{host_sdk_dir.resolve().as_posix()}"
    )
