from __future__ import annotations

from typing import Any, cast

from .base import TemplateScaffolder, TemplateScaffoldRequest, TemplateScaffoldResult


class WebTemplateScaffolder(TemplateScaffolder):
    @property
    def app_type(self) -> str:
        return "web"

    async def scaffold(self, request: TemplateScaffoldRequest) -> TemplateScaffoldResult:
        self.copy_template_tree(request.template_source, request.target_dir)

        manifest_path = request.target_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Template manifest.json missing")
        manifest = self.load_json(manifest_path)
        old_plugin_id = str(manifest.get("id") or request.template_id)
        manifest["id"] = request.plugin_id
        manifest["name"] = request.app_name.strip() or request.plugin_id
        manifest["description"] = request.app_description.strip()
        manifest["author"] = request.owner_email.strip() or manifest.get("author", "")
        manifest["app_type"] = self.app_type
        preview_cfg = cast(dict[str, Any], manifest.get("preview")) if isinstance(manifest.get("preview"), dict) else {}
        preview_cfg["frontend_dir"] = str(preview_cfg.get("frontend_dir") or "web-src")
        manifest["preview"] = preview_cfg
        self.write_json(manifest_path, manifest)

        package_json_path = request.target_dir / "web-src" / "package.json"
        if package_json_path.exists():
            package_json = self.load_json(package_json_path)
            package_json["name"] = self.normalize_package_name(request.plugin_id)
            if request.app_description.strip():
                package_json["description"] = request.app_description.strip()
            package_json["version"] = "0.1.0"
            self.write_json(package_json_path, package_json)

        self.replace_plugin_id_references(request.target_dir, old_plugin_id, request.plugin_id)
        return TemplateScaffoldResult(
            plugin_id=request.plugin_id,
            app_type=self.app_type,
            target_dir=request.target_dir,
        )
