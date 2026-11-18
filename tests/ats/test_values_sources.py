"""Checks of how values_sources reads a HelmRelease's `valuesFrom` entries; they need no
cluster."""

import base64

import pytest
from helm_values import merged_values
from node_pools import node_pools
from values_sources import ValuesSourceError
from values_testdata import STAGE, config_map, helm_release, lookup_for, ref


def test_values_come_from_the_helm_release_namespace() -> None:
    lookup = lookup_for({("ConfigMap", "stage"): STAGE})
    hr = helm_release(ref("stage"))
    hr["metadata"]["namespace"] = "elsewhere"
    with pytest.raises(ValuesSourceError, match="'elsewhere/stage'"):
        merged_values(hr, lookup)


def test_secret_values_are_decoded() -> None:
    secret = {"data": {"values": base64.b64encode(b"a: 1\n").decode()}}
    lookup = lookup_for({("Secret", "s"): secret})
    assert merged_values(helm_release(ref("s", kind="Secret")), lookup) == {"a": 1}


@pytest.mark.parametrize(
    "objects",
    [
        {},  # no object
        {("ConfigMap", "cm"): config_map("a: 1", key="other")},  # no key
        {("ConfigMap", "cm"): {}},  # no data
    ],
)
def test_optional_entry_without_values_is_skipped(objects: dict) -> None:
    hr = helm_release(ref("cm", optional=True), ref("stage"))
    lookup = lookup_for({**objects, ("ConfigMap", "stage"): STAGE})
    assert node_pools(merged_values(hr, lookup)) == {"nodepool0"}


@pytest.mark.parametrize(
    "objects, entry, message",
    [
        ({}, ref("cm"), "'org-org-name/cm': the object or its key 'values' is missing"),
        ({("ConfigMap", "cm"): {}}, ref("cm"), "its key 'values' is missing"),
        ({("ConfigMap", "cm"): STAGE}, ref("cm", targetPath="a.b"), "targetPath"),
        ({("ConfigMap", "cm"): config_map("[1]")}, ref("cm"), "aren't a map"),
        ({}, ref("cm", kind="Bucket"), "only ConfigMaps and Secrets"),
        ({("ConfigMap", "cm"): config_map("a: [")}, ref("cm"), "aren't valid YAML"),
        (
            {("Secret", "s"): config_map(base64.b64encode(b"\xff").decode())},
            ref("s", kind="Secret"),
            "can't be decoded",
        ),
        ({}, {"kind": "ConfigMap"}, "has no name"),
    ],
)
def test_entry_that_cant_be_read_fails(
    objects: dict, entry: dict, message: str
) -> None:
    with pytest.raises(ValuesSourceError, match=message):
        merged_values(helm_release(entry), lookup_for(objects))
