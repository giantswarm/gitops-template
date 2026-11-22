"""Checks of how cluster_gates judges the Kustomizations and base apps of the clusters with apps;
they need no cluster."""

from cluster_gates import (
    Gate,
    base_app_problems,
    gates_in_cluster,
    held_problems,
    opened_problems,
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


def owned_by(owner: str) -> dict:
    return {"metadata": {"labels": {"kustomize.toolkit.fluxcd.io/name": owner}}}


def test_base_app_problems() -> None:
    gate = Gate(
        "org-org-name",
        "wc",
        "cluster",
        ["org-org-name/apps"],
        ["wc-crds", "wc-gateway"],
    )
    hrs: dict[str, dict] = {
        "org-org-name/wc-crds": owned_by("cluster"),
        "org-org-name/wc-other": {"metadata": {}},
    }
    assert base_app_problems(gate, hrs) == [
        "base app HelmRelease 'org-org-name/wc-gateway' isn't applied by 'cluster' while "
        "the cluster isn't Available: its owner is None"
    ]
    hrs["org-org-name/wc-gateway"] = owned_by("apps")
    assert base_app_problems(gate, hrs) == [
        "base app HelmRelease 'org-org-name/wc-gateway' isn't applied by 'cluster' while "
        "the cluster isn't Available: its owner is apps"
    ]


def gated(name: str, namespace: str, **spec: object) -> dict:
    return {"metadata": {"name": name, "namespace": namespace}, "spec": spec}


def test_gates_in_cluster_follow_the_cluster_health_checks() -> None:
    cluster_check = {"apiVersion": "cluster.x-k8s.io/v1beta2", "kind": "Cluster"}
    kustomizations = {
        "org-acme/mc-clusters-prod": gated(
            "mc-clusters-prod",
            "org-acme",
            dependsOn=[{"name": "mc-organization-acme", "namespace": "default"}],
            healthChecks=[{**cluster_check, "name": "prod", "namespace": "org-acme"}],
        ),
        "org-acme/mc-clusters-prod-apps": gated(
            "mc-clusters-prod-apps",
            "org-acme",
            dependsOn=[{"name": "mc-clusters-prod"}],
        ),
        # health-checks a Cluster in its own namespace when the check names none
        "org-acme/mc-clusters-dev": gated(
            "mc-clusters-dev",
            "org-acme",
            healthChecks=[{**cluster_check, "name": "dev"}],
        ),
        # depends on a Kustomization of the same name in another namespace: not the gate
        "default/other": gated(
            "other", "default", dependsOn=[{"name": "mc-clusters-prod"}]
        ),
        "default/mc-organization-acme": gated("mc-organization-acme", "default"),
    }
    assert gates_in_cluster(kustomizations, {"org-acme/prod": ["prod-crds"]}) == [
        Gate("org-acme", "dev", "mc-clusters-dev", [], []),
        Gate(
            "org-acme",
            "prod",
            "mc-clusters-prod",
            ["org-acme/mc-clusters-prod-apps"],
            ["prod-crds"],
        ),
    ]
