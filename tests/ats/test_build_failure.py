"""Checks of how test_prune P2 judges the management cluster's Kustomization when it can't
build the organisation without its Organization, and the organisation's namespace Kustomization,
which waits for it; they need no cluster."""

from flux_inventory import build_failure_problems, dependency_wait_problems

ORGANIZATION = ("Organization", "", "org-name")
NAMESPACE = ("Kustomization", "default", "mc-name-organization-org-name")
CLUSTER = ("Kustomization", "org-org-name", "mc-name-clusters-wc")


def _root(ready: dict, ids: list[str], name: str = "mc-name-gitops") -> dict:
    return {
        "metadata": {"name": name, "namespace": "default"},
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
    "default_mc-name-organization-org-name_kustomize.toolkit.fluxcd.io_Kustomization",
]


def test_build_failure_problems_failed_build_keeps_inventory() -> None:
    assert (
        build_failure_problems(_root(FAILED, INVENTORY), {ORGANIZATION, NAMESPACE})
        == []
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
        _root(FAILED, INVENTORY[:1]), {ORGANIZATION, NAMESPACE}
    ) == [
        "Kustomization 'default/mc-name-gitops' no longer lists "
        "[('Kustomization', 'default', 'mc-name-organization-org-name')] in its inventory"
    ]


WAITING = {"type": "Ready", "status": "False", "reason": "DependencyNotReady"}
NAMESPACE_INVENTORY = [
    "org-org-name_mc-name-clusters-wc_kustomize.toolkit.fluxcd.io_Kustomization"
]


def _namespace(ready: dict, ids: list[str]) -> dict:
    return _root(ready, ids, "mc-name-organization-org-name")


def test_dependency_wait_problems_waiting_keeps_inventory() -> None:
    assert (
        dependency_wait_problems(_namespace(WAITING, NAMESPACE_INVENTORY), {CLUSTER})
        == []
    )


def test_dependency_wait_problems_other_reason() -> None:
    assert dependency_wait_problems(
        _namespace(FAILED, NAMESPACE_INVENTORY), {CLUSTER}
    ) == [
        "Kustomization 'default/mc-name-organization-org-name' doesn't wait for a "
        "dependency: Ready is False (BuildFailed)"
    ]


def test_dependency_wait_problems_pruned() -> None:
    assert dependency_wait_problems(_namespace(WAITING, []), {CLUSTER}) == [
        "Kustomization 'default/mc-name-organization-org-name' no longer lists "
        "[('Kustomization', 'org-org-name', 'mc-name-clusters-wc')] in its inventory"
    ]
