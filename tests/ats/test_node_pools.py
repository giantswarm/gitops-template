"""Checks of how node_pools compares the node pools it finds with the expected ones; they need
no cluster."""

import node_pools as node_pools_module
import pytest
from helm_values import ValuesSourceError
from node_pools import (
    EXPECTED_NODE_POOLS,
    node_pool_problems,
    node_pools,
    workload_cluster_node_pools,
)


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


def test_node_pools_leaves_out_null_pools() -> None:
    # Helm's coalescing deletes a key set to null, so the pool isn't created
    values: dict = {"global": {"nodePools": {"nodepool0": {}, "large": None}}}
    assert node_pools(values) == {"nodepool0"}


def test_node_pool_problems_ignored_cluster() -> None:
    ignored = "org-org-name/hello-app-dev-1"
    actual = {k: v for k, v in EXPECTED_NODE_POOLS.items() if k != ignored}
    assert node_pool_problems(actual, [ignored]) == []


def test_workload_cluster_node_pools_reports_each_unreadable_cluster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def merged(hr: dict, lookup: object) -> dict:
        if hr["name"] == "good":
            return {"global": {"nodePools": {"workers": {}}}}
        raise ValuesSourceError({"name": hr["name"]}, "ns", "missing")

    monkeypatch.setattr(node_pools_module, "classify", lambda hr, lookup: "H2")
    monkeypatch.setattr(node_pools_module, "merged_values", merged)
    hrs = {
        "ns/bad1": {"name": "bad1"},
        "ns/good": {"name": "good"},
        "ns/bad2": {"name": "bad2"},
    }
    pools, problems = workload_cluster_node_pools(hrs, lambda *_: None)
    assert pools == {"ns/good": {"workers"}}
    assert [p.split(":")[0] for p in problems] == [
        "workload cluster 'ns/bad1'",
        "workload cluster 'ns/bad2'",
    ]
