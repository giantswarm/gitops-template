"""The node pools of every workload cluster, as Flux applies them in the kind test.

A cluster's node pools come from several ConfigMaps in the `valuesFrom` of its HelmRelease: the
stage sets `nodepool0`, and a production cluster's region adds an extra pool. No assertion file
shows the result, so this check reads the HelmRelease and its ConfigMaps from the test cluster,
merges them as helm-controller does and compares the node pools with `EXPECTED_NODE_POOLS`.

test_flux_objects.py runs the check with that module's fixtures: after Flux has applied the
repository and the HelmReleases' references have been checked.
"""

from collections.abc import Collection

import pykube
from checks import waits
from checks.helm_release_classes import classify
from checks.helm_release_sources import Lookup, cluster_lookup
from helm_values import ValuesSourceError, merged_values
from pytest_helm_charts.flux.helm_release import HelmReleaseCR

# The node pools in the values of each workload cluster's HelmRelease, by `namespace/name`.
#  Every cluster has to be listed. Production clusters get the stage's `nodepool0` and their
#  region's extra pool. Dev and staging have no pools of their own and get the chart's defaults.
EXPECTED_NODE_POOLS: dict[str, set[str]] = {
    "org-org-name/hello-app-prod-euc": {"nodepool0", "large"},
    "org-org-name/hello-app-prod-usw": {"nodepool0", "large"},
    "org-org-name/hello-app-dev-1": set(),
    "org-org-name/hello-app-staging-1": set(),
    "org-org-name/capi-wc-name": {"workers"},
    "org-org-name/out-of-band-flux-app": {"workers"},
    "org-org-name/out-of-band-no-flux": {"workers"},
}


def node_pools(values: dict) -> set[str]:
    """The node pools in `values`. Helm's coalescing deletes a key set to null, so a pool set
    to null isn't one."""
    pools = (values.get("global") or {}).get("nodePools") or {}
    return {name for name, pool in pools.items() if pool is not None}


def node_pool_problems(
    actual: dict[str, set[str]], ignored: Collection[str] = ()
) -> list[str]:
    """How the node pools of the clusters found differ from `EXPECTED_NODE_POOLS`. An ignored
    cluster isn't missing."""
    problems = [
        f"workload cluster '{k}' isn't in EXPECTED_NODE_POOLS"
        for k in sorted(actual.keys() - EXPECTED_NODE_POOLS.keys())
    ]
    problems += [
        f"workload cluster '{k}' has no HelmRelease"
        for k in sorted(EXPECTED_NODE_POOLS.keys() - actual.keys() - set(ignored))
    ]
    problems += [
        f"workload cluster '{k}' has node pools {sorted(pools)}, "
        f"expected {sorted(EXPECTED_NODE_POOLS[k])}"
        for k, pools in sorted(actual.items())
        if k in EXPECTED_NODE_POOLS and pools != EXPECTED_NODE_POOLS[k]
    ]
    return problems


def workload_cluster_node_pools(
    hrs: dict[str, dict], lookup: Lookup
) -> tuple[dict[str, set[str]], list[str]]:
    """The node pools of each HelmRelease in `hrs` that creates a workload cluster, and the
    clusters whose values can't be read, so that one doesn't hide the others."""
    pools: dict[str, set[str]] = {}
    problems: list[str] = []
    for k, hr in hrs.items():
        if classify(hr, lookup) != "H2":
            continue
        try:
            pools[k] = node_pools(merged_values(hr, lookup))
        except (ValuesSourceError, AttributeError, TypeError) as e:
            problems.append(f"workload cluster '{k}': can't read its node pools: {e}")
    return pools, problems


def node_pool_problems_in_cluster(
    api: pykube.HTTPClient, ignored: Collection[str]
) -> list[str]:
    """How the node pools of the workload clusters' HelmReleases in `api` differ from the
    expected ones. The `ignored` HelmReleases aren't checked."""
    hrs = waits.list_objects(api, HelmReleaseCR, ignored)
    pools, problems = workload_cluster_node_pools(hrs, cluster_lookup(api))
    return problems + node_pool_problems(pools, ignored)
