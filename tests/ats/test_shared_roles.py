"""Checks of the Roles the `automation` ServiceAccounts of the organisations share; they need no
cluster."""

import pytest
from rbac_testdata import objects, ref, sa

WITHOUT_GIANTSWARM = {"default", "org-a", "kube-system"}


@pytest.mark.parametrize(
    "namespace, name",
    [
        ("giantswarm", "patch-charts"),
        ("giantswarm", "write-policy-exceptions"),
        ("kube-system", "write-policy-exceptions"),
    ],
)
def test_shared_role_lists_every_org_automation_account(
    namespace: str, name: str
) -> None:
    got = objects(["default", "org-a", "org-b"])
    assert ("Role", namespace, name) in got
    rb = got[("RoleBinding", namespace, name)]
    assert rb["roleRef"] == ref("Role", name)
    assert rb["subjects"] == [sa("org-a"), sa("org-b")]


@pytest.mark.parametrize(
    "namespace, name, expected",
    [
        ("kube-system", "write-policy-exceptions", True),
        ("policy-exceptions", "write-policy-exceptions", False),
        ("giantswarm", "patch-charts", False),
    ],
)
def test_shared_role_needs_its_namespace(
    namespace: str, name: str, expected: bool
) -> None:
    got = objects(["default", "org-a"], WITHOUT_GIANTSWARM)
    assert (("RoleBinding", namespace, name) in got) is expected


def test_no_shared_roles_without_org_namespaces() -> None:
    assert ("RoleBinding", "giantswarm", "patch-charts") not in objects(["default"])
