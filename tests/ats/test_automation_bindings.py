"""Checks of the objects that give the `automation` ServiceAccounts of `default` and of the
organisation namespaces their rights; they need no cluster."""

import pytest
from automation_bindings import NotAutomationNamespaceError, automation_rbac_objects
from rbac_testdata import CORE, objects, ref, sa


def test_no_cluster_admin_cluster_role_binding() -> None:
    for (kind, _, _), o in objects(["default", "org-a"]).items():
        if kind == "ClusterRoleBinding":
            assert o["roleRef"]["name"] != "cluster-admin"


@pytest.mark.parametrize("namespace", ["default", "org-a"])
def test_service_account(namespace: str) -> None:
    assert ("ServiceAccount", namespace, "automation") in objects(["default", "org-a"])


@pytest.mark.parametrize(
    "namespaces, subjects",
    [
        # `default/automation` is cluster-admin in `default` by a RoleBinding only
        (["default"], [sa("default")]),
        # an organisation's namespace binds both `automation` accounts
        (["default", "org-a"], [sa("org-a"), sa("default")]),
        # the protected namespace drops `default/automation`
        (["default", "org-giantswarm"], [sa("org-giantswarm")]),
    ],
)
def test_write_all(namespaces: list[str], subjects: list[dict]) -> None:
    key = ("RoleBinding", namespaces[-1], "write-all-customer-sa")
    rb = objects(namespaces)[key]
    assert rb["roleRef"] == ref("ClusterRole", "cluster-admin")
    assert rb["subjects"] == subjects


def test_flux_app_bindings_of_default_automation() -> None:
    got = objects(["default"], {"default", "flux-giantswarm"})
    rb = got[("RoleBinding", "default", "flux-crd-controller")]
    assert rb["roleRef"] == ref("ClusterRole", "crd-controller-giantswarm")
    assert rb["subjects"] == [sa("default")]
    assert ("ClusterRole", "", "crd-controller-giantswarm") in got
    logs = got[("RoleBinding", "flux-giantswarm", "read-flux-logs-automation")]
    assert logs["subjects"] == [sa("default")]


def test_namespaces_other_than_default_and_org_are_refused() -> None:
    # rbac-operator creates `automation` in `default` and the `org-*` namespaces only
    with pytest.raises(NotAutomationNamespaceError, match="team-a"):
        automation_rbac_objects(["default", "team-a"], {"default"}, [CORE])
