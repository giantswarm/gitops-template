"""Checks of the assertion comparison itself; they need no cluster."""

from typing import Any

import pytest

from test_flux_objects import assert_objects


class FakeObject:
    def __init__(self, obj: dict) -> None:
        self.obj = obj


def config_map(data: dict[str, Any]) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "cm", "namespace": "ns"},
        "data": data,
    }


@pytest.mark.parametrize(
    "expected, actual",
    [
        # a block scalar written as `|` in the assertion, `|-` in the repository
        ("a: 1\nb: 2\n", "a: 1\nb: 2"),
        # a stray space at the end of a line
        ("a: 1 \nb: 2\n", "a: 1\nb: 2\n"),
    ],
)
def test_values_ignore_trailing_whitespace(expected: str, actual: str) -> None:
    assert_objects(
        config_map({"values": expected}),
        FakeObject(config_map({"values": actual})),  # type: ignore[arg-type]
        "test",
    )


@pytest.mark.parametrize(
    "expected, actual",
    [
        # single-line values, such as a Secret's base64 `values`
        ({"values": "a: 1"}, {"values": "a: 2"}),
        # a multi-line value
        ({"values": "a: 1\nb: 2\n"}, {"values": "a: 1\nb: 3\n"}),
        # indentation is meaningful in YAML values
        ({"values": "a:\n  b: 1\n"}, {"values": "a:\nb: 1\n"}),
        # another key next to a `values` that differs only in trailing whitespace
        ({"values": "a: 1\n", "other": "x"}, {"values": "a: 1", "other": "y"}),
    ],
)
def test_values_changes_fail(expected: dict, actual: dict) -> None:
    with pytest.raises(pytest.fail.Exception):
        assert_objects(
            config_map(expected),
            FakeObject(config_map(actual)),  # type: ignore[arg-type]
            "test",
        )


def helm_release(value_sources: list[str], extra: dict | None = None) -> dict:
    spec: dict[str, Any] = {
        "valuesFrom": [
            {"kind": "ConfigMap", "name": n, "valuesKey": "values"}
            for n in value_sources
        ]
    }
    spec.update(extra or {})
    return {
        "apiVersion": "helm.toolkit.fluxcd.io/v2",
        "kind": "HelmRelease",
        "metadata": {"name": "hr", "namespace": "ns"},
        "spec": spec,
    }


def test_values_from_order_matters() -> None:
    # Helm merges `valuesFrom` in order, so a reordered list is a different release.
    with pytest.raises(pytest.fail.Exception):
        assert_objects(
            helm_release(["base", "region", "user"]),
            FakeObject(helm_release(["base", "user", "region"])),  # type: ignore[arg-type]
            "test",
        )


def test_other_lists_ignore_order() -> None:
    expected = helm_release(["base"], {"dependsOn": [{"name": "a"}, {"name": "b"}]})
    actual = helm_release(["base"], {"dependsOn": [{"name": "b"}, {"name": "a"}]})
    assert_objects(expected, FakeObject(actual), "test")  # type: ignore[arg-type]
