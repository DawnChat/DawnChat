from app.plugins.versioning import is_version_newer, parse_semver_tuple


def test_parse_semver_tuple_handles_prefix_and_suffix() -> None:
    assert parse_semver_tuple("v1.2.3") == (1, 2, 3)
    assert parse_semver_tuple("2.4.0-beta.1") == (2, 4, 0)


def test_parse_semver_tuple_fills_missing_segments() -> None:
    assert parse_semver_tuple("1") == (1, 0, 0)
    assert parse_semver_tuple("1.9") == (1, 9, 0)


def test_is_version_newer_compares_as_expected() -> None:
    assert is_version_newer("1.2.0", "1.1.9") is True
    assert is_version_newer("v1.2.0", "1.2.0") is False
    assert is_version_newer("1.2.0", "1.2.0-alpha") is False
