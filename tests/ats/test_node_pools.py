"""Checks of the node pools each workload cluster gets; they need no cluster.

A cluster's node pools come from several `valuesFrom` ConfigMaps of its HelmRelease: the stage
sets `nodepool0`, and a production cluster's region adds an extra pool. The test merges the
values the way helm-controller does and checks the node pools in the result.

The objects come from the assertion files, which the kind test compares with what Flux applies
from the repository, `valuesFrom` order included. So the files stand for the rendered repository.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
CLUSTERS_ASSERTIONS_DIR = HERE / "assertions/exists/organizations/workload-clusters"
# conftest creates the `cluster-app-installation-values` ConfigMap from this file, as the
#  management cluster has its own; it isn't in the assertion files.
INSTALLATION_VALUES_CONFIG_MAP_NAME = "cluster-app-installation-values"
INSTALLATION_VALUES_FILE = (
    HERE.parent.parent / "tools/values-stubs/cluster-app-installation-values.yaml"
)

# The node pools in each cluster's values. Production clusters get the stage's `nodepool0` and
#  their region's extra pool; the other clusters only their own. A cluster without any gets the
#  chart's default node pools.
EXPECTED_NODE_POOLS: dict[str, set[str]] = {
    "hello-app-prod-euc": {"nodepool0", "large"},
    "hello-app-prod-usw": {"nodepool0", "large"},
    "hello-app-dev-1": set(),
    "hello-app-staging-1": set(),
    "capi-wc-name": {"workers"},
}

# (kind, name) -> the object in the HelmRelease's namespace, or None if it doesn't exist
Lookup = Callable[[str, str], dict | None]


class UnsupportedValuesSourceError(NotImplementedError):
    def __init__(self, entry: dict) -> None:
        super().__init__(f"valuesFrom entry {entry} isn't supported")


class MissingValuesSourceError(LookupError):
    def __init__(self, entry: dict) -> None:
        super().__init__(f"valuesFrom {entry['kind']} '{entry['name']}' doesn't exist")


def merge_maps(a: dict, b: dict) -> dict:
    """`b` merged into `a` as helm-controller merges values: maps are merged, anything else in
    `b` replaces what is in `a`."""
    out = dict(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_maps(out[key], value)
        else:
            out[key] = value
    return out


def values_from_entry(entry: dict, lookup: Lookup) -> dict:
    """The values of one `valuesFrom` entry, or {} for a missing optional one. The cluster
    HelmReleases only read ConfigMaps, so another kind or a `targetPath` fails the test.
    """
    if entry["kind"] != "ConfigMap" or entry.get("targetPath"):
        raise UnsupportedValuesSourceError(entry)
    obj = lookup(entry["kind"], entry["name"])
    if obj is None:
        if entry.get("optional"):
            return {}
        raise MissingValuesSourceError(entry)
    return yaml.safe_load(obj["data"][entry.get("valuesKey", "values.yaml")]) or {}


def merged_values(hr: dict, lookup: Lookup) -> dict:
    """The values helm-controller gives the chart of `hr`: every `valuesFrom` entry in order,
    then `spec.values`."""
    values: dict[str, Any] = {}
    for entry in hr["spec"].get("valuesFrom") or []:
        values = merge_maps(values, values_from_entry(entry, lookup))
    return merge_maps(values, hr["spec"].get("values") or {})


def cluster_objects(cluster: str) -> tuple[dict, Lookup]:
    """The cluster's HelmRelease, and a lookup of the objects in its assertion files."""
    objects: dict[tuple[str, str], dict] = {}
    for file in sorted((CLUSTERS_ASSERTIONS_DIR / cluster).glob("*.yaml")):
        for obj in yaml.safe_load_all(file.read_text()):
            if obj:
                objects[(obj["kind"], obj["metadata"]["name"])] = obj
    objects[("ConfigMap", INSTALLATION_VALUES_CONFIG_MAP_NAME)] = {
        "data": {"values.yaml": INSTALLATION_VALUES_FILE.read_text()}
    }

    def lookup(kind: str, name: str) -> dict | None:
        return objects.get((kind, name))

    return objects[("HelmRelease", cluster)], lookup


def node_pools(cluster: str) -> set[str]:
    hr, lookup = cluster_objects(cluster)
    return set(merged_values(hr, lookup).get("global", {}).get("nodePools") or {})


def test_merge_maps_merges_maps_and_replaces_the_rest() -> None:
    a = {"global": {"nodePools": {"a": {"minSize": 1}}, "list": [1, 2]}, "x": 1}
    b = {"global": {"nodePools": {"b": {}}, "list": [3]}, "x": {"y": 2}}
    assert merge_maps(a, b) == {
        "global": {"nodePools": {"a": {"minSize": 1}, "b": {}}, "list": [3]},
        "x": {"y": 2},
    }


def test_node_pools() -> None:
    actual = {cluster: node_pools(cluster) for cluster in EXPECTED_NODE_POOLS}
    assert actual == EXPECTED_NODE_POOLS
