"""Checks of how helm_values merges a HelmRelease's values, and of the node pool comparison;
they need no cluster."""

import base64

import pytest
from helm_values import Lookup, ValuesSourceError, merge_maps, merged_values
from node_pools import EXPECTED_NODE_POOLS, node_pool_problems, node_pools

NAMESPACE = "org-org-name"


def config_map(values: str, key: str = "values") -> dict:
    return {"data": {key: values}}


def lookup_for(objects: dict[tuple[str, str], dict]) -> Lookup:
    """A lookup of `objects` by (kind, name), in NAMESPACE only."""

    def lookup(kind: str, namespace: str, name: str) -> dict | None:
        return objects.get((kind, name)) if namespace == NAMESPACE else None

    return lookup


def helm_release(*entries: dict, values: dict | None = None) -> dict:
    spec: dict = {"valuesFrom": list(entries)}
    if values is not None:
        spec["values"] = values
    return {"metadata": {"name": "hr", "namespace": NAMESPACE}, "spec": spec}


def ref(name: str, kind: str = "ConfigMap", **extra: object) -> dict:
    return {"kind": kind, "name": name, "valuesKey": "values", **extra}


STAGE = config_map("global:\n  nodePools:\n    nodepool0:\n      minSize: 10\n")
REGION = config_map("global:\n  nodePools:\n    large:\n      minSize: 1\n")


def test_merge_maps_merges_maps_and_replaces_the_rest() -> None:
    a = {"global": {"nodePools": {"a": {"minSize": 1}}, "list": [1, 2]}, "x": 1}
    b = {"global": {"nodePools": {"b": {}}, "list": [3]}, "x": {"y": 2}}
    assert merge_maps(a, b) == {
        "global": {"nodePools": {"a": {"minSize": 1}, "b": {}}, "list": [3]},
        "x": {"y": 2},
    }


def test_values_from_entries_merge_in_order_then_spec_values() -> None:
    lookup = lookup_for(
        {("ConfigMap", "region"): REGION, ("ConfigMap", "stage"): STAGE}
    )
    hr = helm_release(
        ref("region"),
        ref("stage"),
        values={"global": {"nodePools": {"extra": {}}}},
    )
    assert node_pools(merged_values(hr, lookup)) == {"nodepool0", "large", "extra"}


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
    ],
)
def test_entry_that_cant_be_read_fails(
    objects: dict, entry: dict, message: str
) -> None:
    with pytest.raises(ValuesSourceError, match=message):
        merged_values(helm_release(entry), lookup_for(objects))


def test_node_pool_problems() -> None:
    assert node_pool_problems(dict(EXPECTED_NODE_POOLS)) == []
    actual = {**EXPECTED_NODE_POOLS, "org-org-name/new": set()}
    actual["org-org-name/hello-app-prod-euc"] = {"nodepool0"}
    del actual["org-org-name/hello-app-dev-1"]
    assert node_pool_problems(actual) == [
        "workload cluster 'org-org-name/new' isn't in EXPECTED_NODE_POOLS",
        "workload cluster 'org-org-name/hello-app-dev-1' has no HelmRelease",
        "workload cluster 'org-org-name/hello-app-prod-euc' has node pools ['nodepool0'], "
        "expected ['large', 'nodepool0']",
    ]
