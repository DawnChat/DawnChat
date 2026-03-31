from __future__ import annotations

import glob
from pathlib import Path

from app.plugins.opencode_rules_service import get_opencode_rules_service


class OpenCodeInstructionResolver:
    def build_workspace_instructions(self, workspace: Path) -> list[str]:
        instructions: list[str] = []
        for rel in ("AGENTS.md", "README.md"):
            if (workspace / rel).exists():
                instructions.append(rel)
        context_glob = workspace / ".opencode" / "context" / "*.md"
        for file_path in sorted(glob.glob(str(context_glob))):
            try:
                rel = Path(file_path).relative_to(workspace).as_posix()
                instructions.append(rel)
            except Exception:
                continue
        return instructions

    def build_shared_instructions(self) -> list[str]:
        instructions: list[str] = []
        rules_dir = get_opencode_rules_service().get_current_dir()
        if not isinstance(rules_dir, str) or not rules_dir.strip():
            return instructions
        context_glob = Path(rules_dir).expanduser() / "context" / "*.md"
        for file_path in sorted(glob.glob(str(context_glob))):
            candidate = Path(file_path)
            if candidate.exists() and candidate.is_file():
                instructions.append(str(candidate.resolve()))
        return instructions

    def resolve_instructions(
        self,
        *,
        workspace: Path | None,
        include_shared_rules: bool,
        include_workspace_rules: bool,
    ) -> list[str]:
        shared = self.build_shared_instructions() if include_shared_rules else []
        workspace_instructions = (
            self.build_workspace_instructions(workspace)
            if include_workspace_rules and workspace is not None
            else []
        )
        return [*shared, *workspace_instructions]
