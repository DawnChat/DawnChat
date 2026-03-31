from __future__ import annotations


def parse_semver_tuple(version: str) -> tuple[int, int, int]:
    normalized = str(version or "").strip()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    parts = normalized.split(".")
    numbers: list[int] = []
    for part in parts:
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        numbers.append(int(digits) if digits else 0)
    while len(numbers) < 3:
        numbers.append(0)
    return numbers[0], numbers[1], numbers[2]


def is_version_newer(candidate: str, baseline: str) -> bool:
    return parse_semver_tuple(candidate) > parse_semver_tuple(baseline)
