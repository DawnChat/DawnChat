#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path


def _load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest is invalid JSON: {path} ({exc})") from exc


def _resolve_asset(data: dict, asset: str, platform: str) -> dict:
    assets = data.get("assets") or {}
    asset_data = assets.get(asset)
    if not isinstance(asset_data, dict):
        raise SystemExit(f"Asset not found in manifest: {asset}")
    platforms = asset_data.get("platforms") or {}
    platform_data = platforms.get(platform)
    if not isinstance(platform_data, dict):
        raise SystemExit(f"Platform not found for asset '{asset}': {platform}")
    return platform_data


def _print_shell_export(values: dict[str, str]) -> None:
    for key, value in values.items():
        print(f"{key}={shlex.quote(str(value))}")


def cmd_get(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    asset = _resolve_asset(manifest, args.asset, args.platform)
    values = {
        "ASSET_NAME": args.asset,
        "ASSET_PLATFORM": args.platform,
        "ASSET_VERSION": asset.get("version", ""),
        "ASSET_URL": asset.get("url", ""),
        "ASSET_SHA256": asset.get("sha256", ""),
        "ASSET_FILENAME": asset.get("filename", ""),
        "ASSET_ARCHIVE_FORMAT": asset.get("archive_format", ""),
        "ASSET_EXTRACT_DIR": asset.get("extract_dir", ""),
        "ASSET_EXECUTABLE": asset.get("executable", ""),
        "ASSET_REQUIRED": str(asset.get("required", False)).lower(),
        "ASSET_PYTHON_VERSION": asset.get("python_version", ""),
    }
    if args.format == "json":
        print(json.dumps(values, ensure_ascii=False))
    else:
        _print_shell_export(values)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resolve runtime asset metadata from manifest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="Get asset metadata")
    get_parser.add_argument("--manifest", required=True, help="Manifest JSON path")
    get_parser.add_argument("--asset", required=True, help="Asset name")
    get_parser.add_argument("--platform", required=True, help="Platform triple")
    get_parser.add_argument("--format", choices=["shell", "json"], default="shell")
    get_parser.set_defaults(func=cmd_get)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
