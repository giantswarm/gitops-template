"""Checks of how helm_values merges a HelmRelease's values; they need no cluster."""

from helm_values import merge_maps, merged_values
from node_pools import node_pools
from values_testdata import REGION, STAGE, helm_release, lookup_for, ref


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
