"""Checks of how the organization-operator stand-in judges the bootstrap; they need no cluster."""

from conftest import organization_init_namespaces
from organization_operator import (
    bootstrapped_problems,
    organization_namespace,
    ready_problems,
    waiting_kustomizations,
    waiting_problems,
)

NAMESPACE = "org-acme"
NOT_FOUND = f'Alert/{NAMESPACE}/a dry-run failed: namespaces "{NAMESPACE}" not found'
FORBIDDEN = (
    'alerts "a" is forbidden: User "system:serviceaccount:default:automation" cannot patch '
    f'resource "alerts" in API group "notification.toolkit.fluxcd.io" in the namespace '
    f'"{NAMESPACE}"'
)
NAME = "golem-organization-acme"


def kustomization(
    name: str, status: str = "", message: str = "", target: str = ""
) -> dict:
    k: dict = {"metadata": {"name": name, "namespace": "default"}, "spec": {}}
    if status:
        k["status"] = {
            "conditions": [{"type": "Ready", "status": status, "message": message}]
        }
    if target:
        k["spec"]["targetNamespace"] = target
    return k


def test_organization_namespace() -> None:
    assert organization_namespace("acme") == "org-acme"


def test_bootstrapped_problems_none_on_a_new_cluster() -> None:
    assert bootstrapped_problems([], ["default", "kube-system"]) == []


def test_bootstrapped_problems_names_what_exists() -> None:
    assert bootstrapped_problems(["acme"], ["default", "org-acme"]) == [
        "Organization 'acme' exists before the bootstrap",
        "Namespace 'org-acme' exists before the bootstrap",
    ]


def test_ready_problems() -> None:
    assert ready_problems(kustomization("golem-gitops", "True"), "golem-gitops") == []
    assert ready_problems(
        kustomization("golem-gitops", "False", "boom"), "golem-gitops"
    ) == ["Kustomization 'default/golem-gitops' isn't ready: Ready is False: boom"]
    assert ready_problems(None, "golem-gitops") == [
        "Kustomization 'golem-gitops' doesn't exist"
    ]


def test_waiting_kustomizations_apply_into_the_namespace() -> None:
    waiting = kustomization(NAME, target=NAMESPACE)
    other = kustomization("golem-organization-other", target="org-other")
    root = kustomization("golem-gitops")
    assert waiting_kustomizations([waiting, other, root], NAMESPACE) == [waiting]


def test_waiting_problems_while_the_namespace_is_missing() -> None:
    # Flux reports the missing namespace, or, as `automation` gets its rights in the namespace
    #  only once it exists, that it may not write there
    assert waiting_problems(kustomization(NAME, "False", NOT_FOUND), NAMESPACE) == []
    assert waiting_problems(kustomization(NAME, "False", FORBIDDEN), NAMESPACE) == []


def test_waiting_problems_ready_without_the_namespace() -> None:
    assert waiting_problems(kustomization(NAME, "True"), NAMESPACE) == [
        f"Kustomization 'default/{NAME}' is Ready without namespace '{NAMESPACE}'"
    ]


def test_waiting_problems_other_failure() -> None:
    k = kustomization(NAME, "False", "kustomize build failed")
    assert waiting_problems(k, NAMESPACE) == [
        f"Kustomization 'default/{NAME}' doesn't wait for namespace "
        f"'{NAMESPACE}': Ready is False: kustomize build failed"
    ]


def test_waiting_problems_before_its_first_reconcile() -> None:
    assert waiting_problems(kustomization(NAME), NAMESPACE) == [
        f"Kustomization 'default/{NAME}' doesn't wait for namespace "
        f"'{NAMESPACE}': has no conditions"
    ]


def test_organization_init_namespaces() -> None:
    # Flux has to bootstrap the organisation's namespace as on a new management cluster, where
    #  only organization-operator creates it
    assert organization_init_namespaces(["default"]) == []
    assert organization_init_namespaces(["default", "org-a", "other"]) == ["org-a"]
