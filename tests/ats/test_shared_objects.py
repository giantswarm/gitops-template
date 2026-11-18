"""Checks of how shared_objects compares a copy with its source; they need no cluster."""

from shared_objects import CONFIG_MAP, copy_problems

SOURCE = {"data": {"ca.crt": "pem"}}


def test_copy_problems_same_data() -> None:
    assert copy_problems(SOURCE, {"data": {"ca.crt": "pem"}}, "org-a") == []


def test_copy_problems_missing_copy() -> None:
    assert copy_problems(SOURCE, None, "org-a") == [
        f"ConfigMap '{CONFIG_MAP}' isn't in namespace 'org-a'"
    ]


def test_copy_problems_other_data() -> None:
    assert copy_problems(SOURCE, {"data": {"ca.crt": "old"}}, "org-a") == [
        f"ConfigMap 'org-a/{CONFIG_MAP}' has other data than its source"
    ]
