"""Checks of how test_prune P2 judges the management cluster's Kustomization when it can't
build the organisation without its Organization; they need no cluster."""

from flux_inventory import build_failure_problems

ORGANIZATION = ("Organization", "", "org-name")
CLUSTER = ("Kustomization", "default", "mc-name-clusters-wc")


def _root(ready: dict, ids: list[str]) -> dict:
    return {
        "metadata": {"name": "mc-name-gitops", "namespace": "default"},
        "status": {
            "conditions": [ready],
            "inventory": {"entries": [{"id": i, "v": "v1"} for i in ids]},
        },
    }


FAILED = {
    "type": "Ready",
    "status": "False",
    "reason": "BuildFailed",
    "message": "kustomize build failed",
}
INVENTORY = [
    "_org-name_security.giantswarm.io_Organization",
    "default_mc-name-clusters-wc_kustomize.toolkit.fluxcd.io_Kustomization",
]


def test_build_failure_problems_failed_build_keeps_inventory() -> None:
    assert (
        build_failure_problems(_root(FAILED, INVENTORY), {ORGANIZATION, CLUSTER}) == []
    )


def test_build_failure_problems_ready() -> None:
    ready = {"type": "Ready", "status": "True", "reason": "ReconciliationSucceeded"}
    assert build_failure_problems(_root(ready, INVENTORY), {ORGANIZATION}) == [
        "Kustomization 'default/mc-name-gitops' doesn't report a failed build: "
        "Ready is True (ReconciliationSucceeded)"
    ]


def test_build_failure_problems_other_failure() -> None:
    other = {"type": "Ready", "status": "False", "reason": "HealthCheckFailed"}
    assert build_failure_problems(_root(other, INVENTORY), {ORGANIZATION}) == [
        "Kustomization 'default/mc-name-gitops' doesn't report a failed build: "
        "Ready is False (HealthCheckFailed)"
    ]


def test_build_failure_problems_pruned() -> None:
    assert build_failure_problems(
        _root(FAILED, INVENTORY[:1]), {ORGANIZATION, CLUSTER}
    ) == [
        "Kustomization 'default/mc-name-gitops' no longer lists "
        "[('Kustomization', 'default', 'mc-name-clusters-wc')] in its inventory"
    ]
