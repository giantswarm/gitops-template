"""Checks of how node_pools compares the node pools it finds with the expected ones; they need
no cluster."""

from node_pools import EXPECTED_NODE_POOLS, node_pool_problems


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
