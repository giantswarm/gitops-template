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


KYVERNO = "write-kyverno-generated-externalsecrets"


def test_kyverno_cluster_role() -> None:
    meta = objects(["default", "org-a"])[("ClusterRole", "", KYVERNO)]["metadata"]
    assert (meta["labels"], list(meta["annotations"])) == (
        {"giantswarm.io/managed-by": "rbac-operator"},
        ["giantswarm.io/notes"],
    )


@pytest.mark.parametrize("namespace", ["org-a", "org-b"])
def test_kyverno_binding_in_each_org_namespace(namespace: str) -> None:
    rb = objects(["default", "org-a", "org-b"])[("RoleBinding", namespace, KYVERNO)]
    assert (rb["roleRef"], rb["subjects"]) == (
        ref("ClusterRole", KYVERNO),
        [sa("kyverno", "kyverno-background-controller")],
    )


def test_no_kyverno_binding_in_default() -> None:
    assert ("RoleBinding", "default", KYVERNO) not in objects(["default", "org-a"])


KYVERNO_TRIGGERS = "list-kyverno-generating-policy-triggers"


def test_kyverno_may_list_secrets_cluster_wide() -> None:
    # a NamespacedGeneratingPolicy lists its triggers across the whole cluster for
    #  generateExisting, so the background controller needs `list` on Secrets cluster-wide
    got = objects(["default", "org-a"])
    role = got[("ClusterRole", "", KYVERNO_TRIGGERS)]
    crb = got[("ClusterRoleBinding", "", KYVERNO_TRIGGERS)]
    assert (role["rules"], crb["roleRef"], crb["subjects"]) == (
        [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["list"]}],
        ref("ClusterRole", KYVERNO_TRIGGERS),
        [sa("kyverno", "kyverno-background-controller")],
    )
