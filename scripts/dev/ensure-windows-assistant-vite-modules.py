#!/usr/bin/env python3
"""
Windows + Bun --linker hoisted: assistant-workspace/node_modules 与 official-plugins/.../web-src
非父子关系，vite.config.* 内 import 无法解析到 store 中的 vite。
在子包 node_modules 中复制 vite 与 @vitejs/plugin-vue（不依赖顶层 node_modules 是否铺平）。
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys


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


def _resolve_vite_src(ws_nm: str, *, want_major: int) -> str | None:
    root = os.path.join(ws_nm, "vite")
    if os.path.isfile(os.path.join(root, "package.json")):
        mj = _vite_major_from_pkg(root)
        if mj == want_major:
            return root
    pat = os.path.join(ws_nm, ".bun", f"vite@{want_major}*", "node_modules", "vite")
    hits = sorted(glob.glob(pat))
    for p in reversed(hits):
        if os.path.isfile(os.path.join(p, "package.json")):
            return p
    return None


def _resolve_plugin_vue_src(ws_nm: str) -> str | None:
    scoped = os.path.join(ws_nm, "@vitejs", "plugin-vue")
    if os.path.isfile(os.path.join(scoped, "package.json")):
        return scoped
    pat = os.path.join(ws_nm, ".bun", "@vitejs+plugin-vue@*", "node_modules", "@vitejs", "plugin-vue")
    hits = sorted(glob.glob(pat))
    for p in reversed(hits):
        if os.path.isfile(os.path.join(p, "package.json")):
            return p
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
        vite_src = _resolve_vite_src(ws_nm, want_major=want_major)
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
