#!/usr/bin/env python3
"""
Analyze package size for DawnChat sidecar/runtime.

Examples:
    python analyze_package_size.py <site_packages_dir>
    python analyze_package_size.py --sidecar-root <sidecar_dir> --top 80
    python analyze_package_size.py <site_packages_dir> --json size.json
    python analyze_package_size.py --sidecar-root <sidecar_dir> --json now.json --compare prev.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import site
import sys
from typing import Any


def get_dir_size(path: Path) -> int:
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def format_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def normalize_package_name(name: str, is_file: bool) -> str:
    normalized = name
    if name.endswith(".dist-info") or name.endswith(".egg-info"):
        normalized = name.split("-")[0]
    elif is_file and name.endswith(".py"):
        normalized = name[:-3]
    return normalized.replace("_", "-").lower()


def sorted_entries_with_ratio(raw_sizes: dict[str, int]) -> tuple[list[dict[str, Any]], int]:
    entries = sorted(raw_sizes.items(), key=lambda x: x[1], reverse=True)
    total = sum(size for _, size in entries)
    out: list[dict[str, Any]] = []
    for name, size in entries:
        percentage = (size / total * 100.0) if total else 0.0
        out.append({"name": name, "size_bytes": size, "percentage": percentage})
    return out, total


def analyze_site_packages(site_packages_dir: Path) -> dict[str, Any]:
    package_sizes: dict[str, int] = {}
    for item in site_packages_dir.iterdir():
        if item.name == "__pycache__":
            continue
        pkg_name = normalize_package_name(item.name, item.is_file())
        package_sizes[pkg_name] = package_sizes.get(pkg_name, 0) + get_dir_size(item)

    entries, total = sorted_entries_with_ratio(package_sizes)
    return {
        "path": str(site_packages_dir),
        "total_size_bytes": total,
        "entries": entries,
    }


def analyze_top_level(root_dir: Path) -> dict[str, Any]:
    top_sizes: dict[str, int] = {}
    for item in root_dir.iterdir():
        top_sizes[item.name] = get_dir_size(item)
    entries, total = sorted_entries_with_ratio(top_sizes)
    return {
        "path": str(root_dir),
        "total_size_bytes": total,
        "entries": entries,
    }


def print_table(title: str, entries: list[dict[str, Any]], total_size: int, top_n: int) -> None:
    print(f"\n{title}")
    print(f"{'Name':<34} {'Size':<12} {'Percentage':>10}")
    print("-" * 62)
    shown = 0
    for entry in entries:
        if shown >= top_n:
            break
        size = entry["size_bytes"]
        pct = entry["percentage"]
        if pct < 0.1 and size < 1024 * 100:
            continue
        print(f"{entry['name']:<34} {format_size(size):<12} {pct:>8.1f}%")
        shown += 1
    print("-" * 62)
    print(f"Total: {format_size(total_size)}")


def to_size_map(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {entry["name"]: int(entry["size_bytes"]) for entry in entries}


def print_diff_table(
    title: str,
    current_entries: list[dict[str, Any]],
    previous_entries: list[dict[str, Any]],
    top_n: int,
) -> None:
    current = to_size_map(current_entries)
    previous = to_size_map(previous_entries)
    keys = set(current) | set(previous)
    changes = []
    for key in keys:
        old = previous.get(key, 0)
        new = current.get(key, 0)
        delta = new - old
        if delta != 0:
            changes.append((key, delta, new, old))
    changes.sort(key=lambda x: abs(x[1]), reverse=True)

    print(f"\n{title}")
    print(f"{'Name':<34} {'Delta':<12} {'Current':<12} {'Previous':<12}")
    print("-" * 78)
    for name, delta, new, old in changes[:top_n]:
        sign = "+" if delta > 0 else ""
        print(f"{name:<34} {sign}{format_size(delta):<12} {format_size(new):<12} {format_size(old):<12}")
    if not changes:
        print("No size changes.")
    print("-" * 78)


def infer_site_packages_from_sidecar(sidecar_root: Path) -> Path:
    candidate = sidecar_root / "python" / "lib" / "python3.11" / "site-packages"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Cannot find site-packages under sidecar root: {sidecar_root}")


def build_analysis_result(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site_packages": None,
        "top_level": None,
    }

    if args.sidecar_root:
        sidecar_root = Path(args.sidecar_root).expanduser().resolve()
        if not sidecar_root.exists():
            raise FileNotFoundError(f"Sidecar root not found: {sidecar_root}")
        result["top_level"] = analyze_top_level(sidecar_root)
        site_packages_dir = Path(args.site_packages).expanduser().resolve() if args.site_packages else infer_site_packages_from_sidecar(sidecar_root)
    else:
        if args.site_packages:
            site_packages_dir = Path(args.site_packages).expanduser().resolve()
        elif args.target:
            site_packages_dir = Path(args.target).expanduser().resolve()
        else:
            site_packages_dir = Path(site.getsitepackages()[0]).resolve()

    if not site_packages_dir.exists():
        raise FileNotFoundError(f"site-packages not found: {site_packages_dir}")
    result["site_packages"] = analyze_site_packages(site_packages_dir)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze DawnChat package/sidecar size.")
    parser.add_argument("target", nargs="?", help="site-packages path (kept for compatibility)")
    parser.add_argument("--site-packages", dest="site_packages", help="explicit site-packages path")
    parser.add_argument("--sidecar-root", dest="sidecar_root", help="sidecar root path, also output top-level size table")
    parser.add_argument("--top", type=int, default=120, help="max rows to show (default: 120)")
    parser.add_argument("--json", dest="json_path", help="write full analysis result to json file")
    parser.add_argument("--compare", dest="compare_json", help="compare with previous json result")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        result = build_analysis_result(args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    site_section = result["site_packages"]
    if args.sidecar_root and result["top_level"] is not None:
        top_level = result["top_level"]
        print(f"Analyzing sidecar root: {top_level['path']}")
        print_table(
            title="Top-Level Composition",
            entries=top_level["entries"],
            total_size=top_level["total_size_bytes"],
            top_n=args.top,
        )

    print(f"\nAnalyzing site-packages: {site_section['path']}")
    print_table(
        title="Site-Packages Composition",
        entries=site_section["entries"],
        total_size=site_section["total_size_bytes"],
        top_n=args.top,
    )

    if args.compare_json:
        compare_path = Path(args.compare_json).expanduser().resolve()
        if not compare_path.exists():
            print(f"\nWARN: compare file not found: {compare_path}")
        else:
            previous = json.loads(compare_path.read_text(encoding="utf-8"))
            prev_site = previous.get("site_packages", {}).get("entries", [])
            print_diff_table(
                title="Diff: Site-Packages",
                current_entries=site_section["entries"],
                previous_entries=prev_site,
                top_n=min(args.top, 80),
            )
            curr_top = result.get("top_level")
            prev_top = previous.get("top_level")
            if curr_top and prev_top:
                print_diff_table(
                    title="Diff: Top-Level",
                    current_entries=curr_top.get("entries", []),
                    previous_entries=prev_top.get("entries", []),
                    top_n=min(args.top, 40),
                )

    if args.json_path:
        output = Path(args.json_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report written to: {output}")


if __name__ == "__main__":
    main()
