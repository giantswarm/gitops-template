"""Checks of how workload_cluster_secrets judges the Secrets pushed into the workload cluster;
they need no cluster."""

import base64

from workload_cluster_secrets import COMMON, GENERATED, pushed_problems

# "x", base64-encoded as a Secret's data is
ENCODED_X = base64.b64encode(b"x").decode()


def test_pushed_problems_none_for_any_value() -> None:
    assert pushed_problems(GENERATED, {"data": {GENERATED.key: ENCODED_X}}) == []


def test_pushed_problems_none_for_the_expected_value() -> None:
    expected = base64.b64encode(COMMON.value.encode()).decode()
    assert pushed_problems(COMMON, {"data": {COMMON.key: expected}}) == []


def test_pushed_problems_missing_secret() -> None:
    assert pushed_problems(GENERATED, None) == [
        f"Secret 'default/{GENERATED.name}' isn't in the workload cluster"
    ]


def test_pushed_problems_empty_value() -> None:
    assert pushed_problems(GENERATED, {"data": {GENERATED.key: ""}}) == [
        f"Secret 'default/{GENERATED.name}' has no '{GENERATED.key}'"
    ]


def test_pushed_problems_no_data() -> None:
    assert pushed_problems(GENERATED, {}) == [
        f"Secret 'default/{GENERATED.name}' has no '{GENERATED.key}'"
    ]


def test_pushed_problems_other_value() -> None:
    assert pushed_problems(COMMON, {"data": {COMMON.key: ENCODED_X}}) == [
        f"Secret 'default/{COMMON.name}' has another '{COMMON.key}' than the store's"
    ]


def test_pushed_problems_value_not_utf8() -> None:
    not_utf8 = base64.b64encode(b"\xff").decode()
    assert pushed_problems(COMMON, {"data": {COMMON.key: not_utf8}}) == [
        f"Secret 'default/{COMMON.name}' has another '{COMMON.key}' than the store's"
    ]
