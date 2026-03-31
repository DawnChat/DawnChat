from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Tuple

from app.agentv3.tools.registry import ToolRegistry, ToolSpec
from app.agentv3.tools.ui import register_ui_tools


def _summarize_text(text: str, limit: int = 300) -> str:
    compact = " ".join(str(text or "").strip().split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def _tool_error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    root_cause_hint: str = "",
    diagnostics: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": False,
        "error": message,
        "error_code": code,
        "retryable": retryable,
        "root_cause_hint": root_cause_hint,
    }
    if diagnostics:
        payload["diagnostics"] = diagnostics
    return payload


def _resolve_workspace(context: Dict[str, Any]) -> Path:
    workspace = str(context.get("workspace_path") or "").strip()
    if not workspace:
        workspace = str(Path.cwd())
    return Path(workspace).expanduser().resolve()


def _resolve_in_workspace(workspace: Path, file_path: str) -> Path:
    raw = Path(file_path)
    if raw.is_absolute():
        resolved = raw.expanduser().resolve()
    else:
        resolved = (workspace / raw).resolve()
    resolved.relative_to(workspace)
    return resolved


async def _tool_read(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    workspace = _resolve_workspace(context)
    file_path = str(arguments.get("file_path") or arguments.get("path") or "")
    if not file_path:
        return _tool_error("missing_file_path", "missing file_path", root_cause_hint="Provide file_path.")
    try:
        target = _resolve_in_workspace(workspace, file_path)
    except Exception:
        return _tool_error(
            "path_outside_workspace",
            "path_outside_workspace",
            root_cause_hint="Use a path inside the workspace.",
        )
    if not target.exists():
        return _tool_error("file_not_found", "file_not_found", root_cause_hint="Check file path and casing.")
    if target.is_dir():
        return _tool_error("path_is_directory", "path_is_directory", root_cause_hint="Use the read tool on a file path.")
    offset = int(arguments.get("offset") or 1)
    limit = int(arguments.get("limit") or 200)
    offset = max(1, offset)
    limit = max(1, min(limit, 2000))
    text = target.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    start = offset - 1
    end = start + limit
    segment = lines[start:end]
    content = "\n".join(f"L{idx}:{line}" for idx, line in enumerate(segment, start=offset))
    return {"ok": True, "data": {"content": content, "path": str(target), "workspace_path": str(workspace)}}


async def _tool_write(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    workspace = _resolve_workspace(context)
    file_path = str(arguments.get("file_path") or arguments.get("path") or "")
    content = str(arguments.get("content") or "")
    mode = str(arguments.get("mode") or "w")
    if not file_path:
        return _tool_error("missing_file_path", "missing file_path", root_cause_hint="Provide file_path.")
    try:
        target = _resolve_in_workspace(workspace, file_path)
    except Exception:
        return _tool_error(
            "path_outside_workspace",
            "path_outside_workspace",
            root_cause_hint="Use a path inside the workspace.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode not in {"w", "a"}:
        mode = "w"
    with open(target, mode, encoding="utf-8") as handle:
        handle.write(content)
    return {
        "ok": True,
        "data": {"path": str(target), "bytes": len(content.encode("utf-8")), "workspace_path": str(workspace)},
    }


async def _tool_bash(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    workspace = _resolve_workspace(context)
    command = str(arguments.get("command") or "").strip()
    if not command:
        return _tool_error("missing_command", "missing command", root_cause_hint="Provide a shell command.")
    timeout_s = int(arguments.get("timeout_seconds") or 20)
    timeout_s = max(1, min(timeout_s, 120))
    process = await asyncio.create_subprocess_exec(
        "/bin/zsh",
        "-lc",
        command,
        cwd=str(workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return _tool_error(
            "command_timeout",
            "command_timeout",
            retryable=True,
            root_cause_hint="Increase timeout_seconds or simplify command.",
        )
    out = (stdout or b"").decode("utf-8", errors="ignore")
    err = (stderr or b"").decode("utf-8", errors="ignore")
    exit_code = int(process.returncode or 0)
    data = {
        "exit_code": exit_code,
        "stdout": out[:20000],
        "stderr": err[:20000],
        "workspace_path": str(workspace),
    }
    if exit_code == 0:
        return {"ok": True, "data": data}
    summary = _summarize_text(err) or _summarize_text(out) or "command failed without output"
    return {
        "ok": False,
        "error": f"bash_nonzero_exit(exit_code={exit_code}): {summary}",
        "error_code": "bash_nonzero_exit",
        "retryable": False,
        "root_cause_hint": "Inspect stderr/stdout and adjust command or arguments.",
        "diagnostics": {
            "exit_code": exit_code,
            "stderr_summary": _summarize_text(err),
            "stdout_summary": _summarize_text(out),
        },
        "data": data,
    }


async def _tool_search(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    workspace = _resolve_workspace(context)
    query = str(arguments.get("query") or arguments.get("pattern") or "").strip()
    if not query:
        return _tool_error("missing_query", "missing_query", root_cause_hint="Provide query/pattern.")
    limit = int(arguments.get("limit") or 50)
    limit = max(1, min(limit, 200))
    is_windows = sys.platform.startswith("win")
    pbs_bin = Path(sys.executable).resolve().parent
    pbs_rg = pbs_bin / ("rg.exe" if is_windows else "rg")
    rg_cmd = (
        str(pbs_rg) if pbs_rg.exists() else None
    ) or shutil.which("rg") or ("/opt/homebrew/bin/rg" if Path("/opt/homebrew/bin/rg").exists() else None) or (
        "/usr/local/bin/rg" if Path("/usr/local/bin/rg").exists() else None
    )
    if not rg_cmd:
        return _tool_error("rg_not_found", "rg_not_found", root_cause_hint="Install ripgrep or bundle rg binary.")

    try:
        process = await asyncio.create_subprocess_exec(
            rg_cmd,
            "--line-number",
            "--no-heading",
            query,
            str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as err:
        return _tool_error("rg_start_failed", f"rg_start_failed: {err}", root_cause_hint="Verify rg executable permissions.")

    stdout, stderr = await process.communicate()
    if process.returncode not in {0, 1}:
        stderr_text = (stderr or b"").decode("utf-8", errors="ignore")[:500]
        return _tool_error(
            "rg_failed",
            stderr_text or "rg_failed",
            root_cause_hint="Check regex syntax and workspace path.",
        )
    rows = (stdout or b"").decode("utf-8", errors="ignore").splitlines()[:limit]
    return {"ok": True, "data": {"matches": rows, "count": len(rows), "workspace_path": str(workspace)}}


def register_native_tools(registry: ToolRegistry) -> None:
    tools: List[Tuple[str, str, str, str, Dict[str, Any], Any]] = [
        (
            "read",
            "Read file content in workspace",
            "files",
            "read",
            {"type": "object", "properties": {"file_path": {"type": "string"}}},
            _tool_read,
        ),
        (
            "write",
            "Write file content in workspace",
            "files",
            "edit",
            {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}},
            _tool_write,
        ),
        (
            "bash",
            "Execute shell command in workspace",
            "shell",
            "bash",
            {"type": "object", "properties": {"command": {"type": "string"}}},
            _tool_bash,
        ),
        (
            "search",
            "Search code in workspace by ripgrep",
            "search",
            "search",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            _tool_search,
        ),
    ]
    for name, description, capability, permission, schema, executor in tools:
        registry.register(
            ToolSpec(
                name=name,
                description=description,
                capability=capability,
                permission=permission,
                input_schema=schema,
                executor=executor,
            )
        )
    register_ui_tools(registry)

