"""Checks of how the organization-operator stand-in judges the bootstrap; they need no cluster."""

from organization_operator import (
    ORG_NAMESPACE,
    ORGANIZATION,
    ORGANIZATION_KUSTOMIZATION,
    ROOT_KUSTOMIZATION,
    bootstrapped_problems,
    organization_problems,
    root_problems,
    waiting_problems,
)

NOT_FOUND = (
    f'Alert/{ORG_NAMESPACE}/a dry-run failed: namespaces "{ORG_NAMESPACE}" not found'
)
FORBIDDEN = (
    'alerts "a" is forbidden: User "system:serviceaccount:default:automation" cannot patch '
    f'resource "alerts" in API group "notification.toolkit.fluxcd.io" in the namespace '
    f'"{ORG_NAMESPACE}"'
)


def kustomization(name: str, status: str, message: str = "") -> dict:
    return {
        "metadata": {"name": name, "namespace": "default"},
        "status": {
            "conditions": [{"type": "Ready", "status": status, "message": message}]
        },
    }


def test_bootstrapped_problems_none_on_a_new_cluster() -> None:
    assert bootstrapped_problems(organization=None, namespace=None) == []


def test_bootstrapped_problems_names_what_exists() -> None:
    assert bootstrapped_problems(organization={}, namespace={}) == [
        f"Organization '{ORGANIZATION}' exists before the bootstrap",
        f"Namespace '{ORG_NAMESPACE}' exists before the bootstrap",
    ]


def test_organization_problems_applied_by_the_root() -> None:
    labels = {"kustomize.toolkit.fluxcd.io/name": ROOT_KUSTOMIZATION}
    assert organization_problems({"metadata": {"labels": labels}}) == []


def test_organization_problems_missing() -> None:
    assert organization_problems(None) == [
        f"Flux hasn't created Organization '{ORGANIZATION}'"
    ]


def test_organization_problems_other_owner() -> None:
    labels = {"kustomize.toolkit.fluxcd.io/name": "other"}
    assert organization_problems({"metadata": {"labels": labels}}) == [
        f"Organization '{ORGANIZATION}' isn't applied by '{ROOT_KUSTOMIZATION}' but by 'other'"
    ]


def test_root_problems() -> None:
    assert root_problems(kustomization(ROOT_KUSTOMIZATION, "True")) == []
    assert root_problems(kustomization(ROOT_KUSTOMIZATION, "False", "boom")) == [
        f"Kustomization 'default/{ROOT_KUSTOMIZATION}' isn't ready: Ready is False: boom"
    ]
    assert root_problems(None) == [
        f"Kustomization '{ROOT_KUSTOMIZATION}' doesn't exist"
    ]


def test_waiting_problems_while_the_namespace_is_missing() -> None:
    # Flux reports the missing namespace, or, as `automation` gets its rights in the namespace
    #  only once it exists, that it may not write there
    name = ORGANIZATION_KUSTOMIZATION
    assert waiting_problems(kustomization(name, "False", NOT_FOUND)) == []
    assert waiting_problems(kustomization(name, "False", FORBIDDEN)) == []


def test_waiting_problems_ready_without_the_namespace() -> None:
    assert waiting_problems(kustomization(ORGANIZATION_KUSTOMIZATION, "True")) == [
        f"Kustomization 'default/{ORGANIZATION_KUSTOMIZATION}' is Ready without namespace "
        f"'{ORG_NAMESPACE}'"
    ]


def test_waiting_problems_other_failure() -> None:
    k = kustomization(ORGANIZATION_KUSTOMIZATION, "False", "kustomize build failed")
    assert waiting_problems(k) == [
        f"Kustomization 'default/{ORGANIZATION_KUSTOMIZATION}' doesn't wait for namespace "
        f"'{ORG_NAMESPACE}': Ready is False: kustomize build failed"
    ]


def test_waiting_problems_before_its_first_reconcile() -> None:
    assert waiting_problems(None) == [
        f"Kustomization '{ORGANIZATION_KUSTOMIZATION}' doesn't exist"
    ]
    k = {"metadata": {"name": ORGANIZATION_KUSTOMIZATION, "namespace": "default"}}
    assert waiting_problems(k) == [
        f"Kustomization 'default/{ORGANIZATION_KUSTOMIZATION}' doesn't wait for namespace "
        f"'{ORG_NAMESPACE}': has no conditions"
    ]
