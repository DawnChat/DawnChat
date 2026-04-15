#!/usr/bin/env python3
"""
Windows + Bun --linker hoisted: assistant-workspace/node_modules 与 official-plugins/.../web-src
非父子关系，vite.config.* 内 import 无法解析到 store 中的 vite。
在子包 node_modules 中复制 vite 与 @vitejs/plugin-vue（不依赖 symlink 权限）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def _copytree(src: str, dst: str) -> None:
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def _vite_major_from_pkg(path: str) -> int | None:
    try:
        with open(os.path.join(path, "package.json"), encoding="utf-8") as f:
            ver = json.load(f).get("version", "")
        return int(ver.split(".", 1)[0]) if ver else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _resolve_vite_src_in_root(nm_root: str, *, want_major: int) -> str | None:
    """在某一 node_modules 根下解析指定 major 的 vite 包目录。"""
    root = os.path.join(nm_root, "vite")
    if os.path.isfile(os.path.join(root, "package.json")):
        mj = _vite_major_from_pkg(root)
        if mj == want_major:
            return root
    candidates: list[str] = []
    bun = os.path.join(nm_root, ".bun")
    if os.path.isdir(bun):
        try:
            for name in os.listdir(bun):
                if not name.startswith("vite@"):
                    continue
                candidate = os.path.join(bun, name, "node_modules", "vite")
                if not os.path.isfile(os.path.join(candidate, "package.json")):
                    continue
                mj = _vite_major_from_pkg(candidate)
                if mj == want_major:
                    candidates.append(candidate)
        except OSError:
            pass
    if candidates:
        return sorted(candidates)[-1]
    return None


def _resolve_vite_src(
    ws_nm: str, *, want_major: int, extra_nm_roots: list[str] | None = None
) -> str | None:
    for nm_root in [ws_nm, *(extra_nm_roots or [])]:
        if not nm_root or not os.path.isdir(nm_root):
            continue
        found = _resolve_vite_src_in_root(nm_root, want_major=want_major)
        if found:
            return found
    return None


def _walk_find_vite_major(search_root: str, want_major: int) -> str | None:
    """递归查找 **/vite/package.json，匹配 major（兜底 Windows hoisted 非常规目录名）。"""
    root = Path(search_root)
    if not root.is_dir():
        return None
    matches: list[str] = []
    try:
        for pkg_json in root.rglob("vite/package.json"):
            vite_dir = str(pkg_json.parent)
            if _vite_major_from_pkg(vite_dir) == want_major:
                matches.append(vite_dir)
    except OSError:
        return None
    if matches:
        return sorted(matches)[-1]
    return None


def _resolve_plugin_vue_src(ws_nm: str) -> str | None:
    scoped = os.path.join(ws_nm, "@vitejs", "plugin-vue")
    if os.path.isfile(os.path.join(scoped, "package.json")):
        return scoped
    bun = os.path.join(ws_nm, ".bun")
    if not os.path.isdir(bun):
        return None
    candidates: list[str] = []
    try:
        for name in os.listdir(bun):
            if name.startswith("@vitejs+plugin-vue@"):
                candidate = os.path.join(
                    bun, name, "node_modules", "@vitejs", "plugin-vue"
                )
                if os.path.isfile(os.path.join(candidate, "package.json")):
                    candidates.append(candidate)
    except OSError:
        return None
    if candidates:
        return sorted(candidates)[-1]
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: ensure-windows-assistant-vite-modules.py <assistant-workspace> <official-plugins-dir>",
            file=sys.stderr,
        )
        return 2
    ws = os.path.abspath(sys.argv[1])
    official = os.path.abspath(sys.argv[2])
    ws_nm = os.path.join(ws, "node_modules")

    plugins = [
        os.path.join(official, "desktop-ai-assistant", "_ir", "frontend", "web-src"),
        os.path.join(official, "web-ai-assistant", "web-src"),
        os.path.join(official, "mobile-ai-assistant", "web-src"),
    ]

    src_pv = _resolve_plugin_vue_src(ws_nm)
    if not src_pv:
        print(f"error: could not resolve @vitejs/plugin-vue under {ws_nm}", file=sys.stderr)
        return 1

    for dest in plugins:
        pkg = os.path.join(dest, "package.json")
        if not os.path.isfile(pkg):
            continue
        nm = os.path.join(dest, "node_modules")
        vite_dst = os.path.join(nm, "vite")
        dst_plugin_vue = os.path.join(nm, "@vitejs", "plugin-vue")

        is_mobile = "mobile-ai-assistant" in dest.replace("\\", "/")
        want_major = 8 if is_mobile else 7
        extra_roots = [os.path.join(dest, "node_modules")] if is_mobile else None
        vite_src = _resolve_vite_src(
            ws_nm, want_major=want_major, extra_nm_roots=extra_roots
        )
        if not vite_src:
            vite_src = _walk_find_vite_major(ws, want_major)
        if not vite_src and is_mobile:
            vite_src = _walk_find_vite_major(dest, want_major)
        if not vite_src:
            print(
                f"error: could not resolve vite major {want_major} for {dest}",
                file=sys.stderr,
            )
            return 1

        if not os.path.isfile(os.path.join(vite_dst, "package.json")):
            os.makedirs(nm, exist_ok=True)
            _copytree(vite_src, vite_dst)

        if not os.path.isfile(os.path.join(dst_plugin_vue, "package.json")):
            os.makedirs(os.path.join(nm, "@vitejs"), exist_ok=True)
            _copytree(src_pv, dst_plugin_vue)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
