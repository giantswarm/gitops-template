"""Checks of how cluster_gate judges the apps Kustomizations, and that its list of them matches
the repository; they need no cluster."""

from pathlib import Path

import yaml
from cluster_gate import (
    GATED_KUSTOMIZATIONS,
    available_condition,
    held_problems,
    opened_problems,
)

WORKLOAD_CLUSTERS_DIR = (
    Path(__file__).resolve().parent
    / "../../management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters"
)
KEY = "default/apps"


def kustomization(reason: str, status: str = "False", inventory: bool = False) -> dict:
    entries = [{"id": "org-org-name_wc-app_helm.toolkit.fluxcd.io_HelmRelease"}]
    return {
        "status": {
            "conditions": [{"type": "Ready", "status": status, "reason": reason}],
            "inventory": {"entries": entries if inventory else []},
        }
    }


def test_held_problems() -> None:
    assert held_problems(KEY, kustomization("DependencyNotReady")) == []
    assert held_problems(KEY, None) == ["Kustomization 'default/apps' doesn't exist"]
    assert held_problems(KEY, kustomization("ReconciliationSucceeded", "True")) == [
        "Kustomization 'default/apps' isn't waiting for its dependency: "
        "Ready is True, ReconciliationSucceeded"
    ]
    assert held_problems(KEY, kustomization("DependencyNotReady", inventory=True)) == [
        "Kustomization 'default/apps' applied [('HelmRelease', 'org-org-name', 'wc-app')] "
        "before the cluster was Available"
    ]


def test_opened_problems() -> None:
    ready = kustomization("ReconciliationSucceeded", "True", inventory=True)
    assert opened_problems(KEY, ready) == []
    assert opened_problems(KEY, kustomization("DependencyNotReady")) == [
        "Kustomization 'default/apps' isn't ready after the cluster was Available: "
        "DependencyNotReady: "
    ]


def test_available_condition_has_a_message() -> None:
    # v1beta2 conditions require `message`, even an empty one
    condition = available_condition("False")
    assert condition["type"] == "Available"
    assert condition["status"] == "False"
    assert condition["message"] == ""


def gates_in_repository() -> dict[str, list[str]]:
    """The `Cluster` each cluster Kustomization health-checks, and the Kustomizations that
    depend on it."""
    kustomizations = []
    for file in sorted(WORKLOAD_CLUSTERS_DIR.glob("*.yaml")):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                kustomizations.append(yaml.safe_load(f))
    clusters = {
        k["metadata"]["name"]: check["name"]
        for k in kustomizations
        for check in k["spec"].get("healthChecks") or []
        if check["kind"] == "Cluster"
    }
    gates: dict[str, list[str]] = {name: [] for name in clusters.values()}
    for k in kustomizations:
        for dependency in k["spec"].get("dependsOn") or []:
            gates[clusters[dependency["name"]]].append(k["metadata"]["name"])
    return {name: sorted(deps) for name, deps in gates.items()}


def test_gated_kustomizations_match_the_repository() -> None:
    expected = {name: sorted(deps) for name, deps in GATED_KUSTOMIZATIONS.items()}
    assert gates_in_repository() == expected
