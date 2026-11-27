"""Checks of how node_pools compares the node pools it finds with the expected ones; they need
no cluster."""

import node_pools as node_pools_module
import pytest
from node_pools import (
    node_pool_problems,
    node_pool_problems_in_cluster,
    node_pools,
    workload_cluster_node_pools,
)
from values_sources import ValuesSourceError

EXPECTED_NODE_POOLS = {
    "org-org-name/hello-app-prod-euc": {"nodepool0", "large"},
    "org-org-name/hello-app-dev-1": set(),
}
EXPECTED = {"org-org-name": EXPECTED_NODE_POOLS}


def test_node_pool_problems() -> None:
    assert node_pool_problems(dict(EXPECTED_NODE_POOLS), EXPECTED) == []
    actual = {**EXPECTED_NODE_POOLS, "org-org-name/new": set()}
    actual["org-org-name/hello-app-prod-euc"] = {"nodepool0"}
    del actual["org-org-name/hello-app-dev-1"]
    assert node_pool_problems(actual, EXPECTED) == [
        "workload cluster 'org-org-name/new' isn't in nodePools of org-org-name in "
        "kind-test.yaml",
        "workload cluster 'org-org-name/hello-app-dev-1' has no HelmRelease",
        "workload cluster 'org-org-name/hello-app-prod-euc' has node pools ['nodepool0'], "
        "expected ['large', 'nodepool0']",
    ]


def test_node_pool_problems_only_in_the_namespaces_listed() -> None:
    # a fork's own organisation isn't checked until kind-test.yaml lists it
    actual = {**EXPECTED_NODE_POOLS, "org-acme/prod": {"nodepool0"}}
    assert node_pool_problems(actual, EXPECTED) == []


def test_node_pool_problems_of_a_namespace_that_isnt_there() -> None:
    # the example organisation is gone: its clusters aren't missing, the check has nothing to do
    assert node_pool_problems({"org-acme/prod": {"nodepool0"}}, EXPECTED) == []


def test_node_pools_leaves_out_null_pools() -> None:
    # Helm's coalescing deletes a key set to null, so the pool isn't created
    values: dict = {"global": {"nodePools": {"nodepool0": {}, "large": None}}}
    assert node_pools(values) == {"nodepool0"}


def test_node_pool_problems_ignored_cluster() -> None:
    ignored = "org-org-name/hello-app-dev-1"
    actual = {k: v for k, v in EXPECTED_NODE_POOLS.items() if k != ignored}
    assert node_pool_problems(actual, EXPECTED, [ignored]) == []


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
    pools, unreadable = workload_cluster_node_pools(hrs, lambda *_: None)
    assert pools == {"ns/good": {"workers"}}
    assert sorted(unreadable) == ["ns/bad1", "ns/bad2"]


def test_unreadable_expected_cluster_is_reported_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreadable = "org-org-name/hello-app-dev-1"
    pools = {k: v for k, v in EXPECTED_NODE_POOLS.items() if k != unreadable}
    monkeypatch.setattr(node_pools_module, "cluster_lookup", lambda api: None)
    monkeypatch.setattr(
        node_pools_module,
        "workload_cluster_node_pools",
        lambda hrs, lookup: (
            pools,
            {unreadable: f"workload cluster '{unreadable}': x"},
        ),
    )
    monkeypatch.setattr(node_pools_module.waits, "list_objects", lambda *_: {})
    assert node_pool_problems_in_cluster(None, (), EXPECTED) == [  # type: ignore[arg-type]
        f"workload cluster '{unreadable}': x"
    ]
