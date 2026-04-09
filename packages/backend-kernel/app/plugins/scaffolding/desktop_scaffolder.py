from __future__ import annotations

from .base import TemplateScaffolder, TemplateScaffoldRequest, TemplateScaffoldResult


class DesktopTemplateScaffolder(TemplateScaffolder):
    @property
    def app_type(self) -> str:
        return "desktop"

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
        self.write_json(manifest_path, manifest)

        pyproject_path = request.target_dir / "pyproject.toml"
        if pyproject_path.exists():
            self.rewrite_pyproject(
                pyproject_path,
                package_name=self.normalize_package_name(request.plugin_id),
                description=request.app_description.strip(),
            )

        self.rewrite_frontend_sdk_dependencies(
            request.target_dir / "_ir" / "frontend" / "web-src" / "package.json",
            plugin_root=request.target_dir,
        )

        self.replace_plugin_id_references(request.target_dir, old_plugin_id, request.plugin_id)

        return TemplateScaffoldResult(
            plugin_id=request.plugin_id,
            app_type=self.app_type,
            target_dir=request.target_dir,
        )
