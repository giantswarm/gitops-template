"""The node pools of every workload cluster, as Flux applies them in the kind test.

A cluster's node pools come from several ConfigMaps in the `valuesFrom` of its HelmRelease: a
production cluster's own values set `nodepool0`, and its region adds an extra pool. No assertion
file shows the result, so this check reads the HelmRelease and its ConfigMaps from the test
cluster, merges them as helm-controller does and compares the node pools with `nodePools` in
kind-test.yaml. In a namespace listed there, every cluster has to be listed; the clusters of
other namespaces, such as a fork's own organisation before it lists them, aren't checked, and
nor is a listed namespace without any cluster, such as the template's example organisation in a
fork that deleted it.

test_flux_objects.py runs the check with that module's fixtures: after Flux has applied the
repository and the HelmReleases' references have been checked.
"""

from collections.abc import Collection

import pykube
from checks import waits
from checks.helm_release_classes import classify
from checks.helm_release_sources import Lookup, cluster_lookup
from helm_values import merged_values
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from values_sources import ValuesSourceError

# The expected node pools of each cluster, `namespace/name`, by namespace
Expected = dict[str, dict[str, set[str]]]


def node_pools(values: dict) -> set[str]:
    """The node pools in `values`. Helm's coalescing deletes a key set to null, so a pool set
    to null isn't one."""
    pools = (values.get("global") or {}).get("nodePools") or {}
    return {name for name, pool in pools.items() if pool is not None}


def node_pool_problems(
    actual: dict[str, set[str]], expected: Expected, ignored: Collection[str] = ()
) -> list[str]:
    """How the node pools of the clusters found differ from the `expected` ones, in the
    namespaces `expected` lists that have a cluster. An ignored cluster isn't missing.
    """
    problems = []
    for namespace, clusters in sorted(expected.items()):
        found = {k: v for k, v in actual.items() if k.split("/")[0] == namespace}
        if not found:
            continue
        problems += [
            f"workload cluster '{k}' isn't in nodePools of {namespace} in kind-test.yaml"
            for k in sorted(found.keys() - clusters.keys())
        ]
        problems += [
            f"workload cluster '{k}' has no HelmRelease"
            for k in sorted(clusters.keys() - found.keys() - set(ignored))
        ]
        problems += [
            f"workload cluster '{k}' has node pools {sorted(pools)}, "
            f"expected {sorted(clusters[k])}"
            for k, pools in sorted(found.items())
            if k in clusters and pools != clusters[k]
        ]
    return problems


def workload_cluster_node_pools(
    hrs: dict[str, dict], lookup: Lookup
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """The node pools of each HelmRelease in `hrs` that creates a workload cluster, and why the
    values of the others can't be read, so that one doesn't hide the others."""
    pools: dict[str, set[str]] = {}
    unreadable: dict[str, str] = {}
    for k, hr in hrs.items():
        if classify(hr, lookup) != "H2":
            continue
        try:
            pools[k] = node_pools(merged_values(hr, lookup))
        except (ValuesSourceError, AttributeError, TypeError) as e:
            unreadable[k] = f"workload cluster '{k}': can't read its node pools: {e}"
    return pools, unreadable


def node_pool_problems_in_cluster(
    api: pykube.HTTPClient, ignored: Collection[str], expected: Expected
) -> list[str]:
    """How the node pools of the workload clusters' HelmReleases in `api` differ from the
    `expected` ones. The `ignored` HelmReleases aren't checked."""
    hrs = waits.list_objects(api, HelmReleaseCR, ignored)
    pools, unreadable = workload_cluster_node_pools(hrs, cluster_lookup(api))
    # an unreadable cluster has a HelmRelease: it isn't missing
    return list(unreadable.values()) + node_pool_problems(
        pools, expected, [*ignored, *unreadable]
    )
