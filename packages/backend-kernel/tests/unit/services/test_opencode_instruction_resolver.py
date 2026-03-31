from pathlib import Path

from app.services.opencode_instruction_resolver import OpenCodeInstructionResolver


class _RulesServiceStub:
    def __init__(self, current_dir: str) -> None:
        self._current_dir = current_dir

    def get_current_dir(self) -> str:
        return self._current_dir


def test_resolve_instructions_merges_shared_and_workspace(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path / "shared-rules"
    (shared_root / "context").mkdir(parents=True, exist_ok=True)
    (shared_root / "context" / "b.md").write_text("b", encoding="utf-8")
    (shared_root / "context" / "a.md").write_text("a", encoding="utf-8")

    workspace = tmp_path / "workspace"
    (workspace / ".opencode" / "context").mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("agents", encoding="utf-8")
    (workspace / "README.md").write_text("readme", encoding="utf-8")
    (workspace / ".opencode" / "context" / "workspace.md").write_text("ctx", encoding="utf-8")

    import app.services.opencode_instruction_resolver as resolver_module

    monkeypatch.setattr(
        resolver_module,
        "get_opencode_rules_service",
        lambda: _RulesServiceStub(str(shared_root)),
    )

    resolver = OpenCodeInstructionResolver()
    merged = resolver.resolve_instructions(
        workspace=workspace,
        include_shared_rules=True,
        include_workspace_rules=True,
    )

    assert merged == [
        str((shared_root / "context" / "a.md").resolve()),
        str((shared_root / "context" / "b.md").resolve()),
        "AGENTS.md",
        "README.md",
        ".opencode/context/workspace.md",
    ]


def test_resolve_instructions_can_exclude_shared(monkeypatch, tmp_path: Path) -> None:
    shared_root = tmp_path / "shared-rules"
    (shared_root / "context").mkdir(parents=True, exist_ok=True)
    (shared_root / "context" / "base.md").write_text("base", encoding="utf-8")

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("agents", encoding="utf-8")

    import app.services.opencode_instruction_resolver as resolver_module

    monkeypatch.setattr(
        resolver_module,
        "get_opencode_rules_service",
        lambda: _RulesServiceStub(str(shared_root)),
    )

    resolver = OpenCodeInstructionResolver()
    merged = resolver.resolve_instructions(
        workspace=workspace,
        include_shared_rules=False,
        include_workspace_rules=True,
    )

    assert merged == ["AGENTS.md"]
