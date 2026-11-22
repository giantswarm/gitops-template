"""Checks of how cluster_gates judges the Kustomizations and base apps of the clusters with apps;
they need no cluster."""

from cluster_gates import Gate, base_app_problems, held_problems, opened_problems

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
        "before the cluster's control plane was up"
    ]


def test_opened_problems() -> None:
    ready = kustomization("ReconciliationSucceeded", "True", inventory=True)
    assert opened_problems(KEY, ready) == []
    assert opened_problems(KEY, kustomization("DependencyNotReady")) == [
        "Kustomization 'default/apps' isn't ready after the cluster's control plane was up: "
        "DependencyNotReady: "
    ]


def owned_by(owner: str) -> dict:
    return {"metadata": {"labels": {"kustomize.toolkit.fluxcd.io/name": owner}}}


def test_base_app_problems() -> None:
    gate = Gate("cluster", "apps", ["wc-crds", "wc-gateway"])
    hrs: dict[str, dict] = {
        "org-org-name/wc-crds": owned_by("cluster"),
        "org-org-name/wc-other": {"metadata": {}},
    }
    assert base_app_problems(gate, hrs) == [
        "base app HelmRelease 'org-org-name/wc-gateway' isn't applied by 'cluster' while "
        "the cluster's control plane isn't up: its owner is None"
    ]
    hrs["org-org-name/wc-gateway"] = owned_by("apps")
    assert base_app_problems(gate, hrs) == [
        "base app HelmRelease 'org-org-name/wc-gateway' isn't applied by 'cluster' while "
        "the cluster's control plane isn't up: its owner is apps"
    ]
