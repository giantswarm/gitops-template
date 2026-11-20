"""Checks of the plan of objects that replicate rbac-operator's RBAC for the `automation`
ServiceAccounts, and of how the fixture brings existing ones in line; they need no cluster.
"""

import pytest
from automation_bindings import NotAutomationNamespaceError, automation_rbac_objects
from automation_rbac import needs_update

CORE = {"groupVersion": "v1", "resources": [{"name": "pods", "verbs": ["get"]}]}


def by_kind_and_name(objects: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {
        (o["kind"], o["metadata"].get("namespace", ""), o["metadata"]["name"]): o
        for o in objects
    }


def sa(namespace: str) -> dict:
    return {"kind": "ServiceAccount", "name": "automation", "namespace": namespace}


def ref(kind: str, name: str) -> dict:
    return {"apiGroup": "rbac.authorization.k8s.io", "kind": kind, "name": name}


def objects(namespaces: list[str], existing: set[str] | None = None) -> dict:
    if existing is None:
        existing = {"default", "giantswarm", "kube-system", *namespaces}
    return by_kind_and_name(automation_rbac_objects(namespaces, existing, [CORE]))


def test_no_cluster_admin_cluster_role_binding() -> None:
    for (kind, _, _), o in objects(["default", "org-a"]).items():
        if kind == "ClusterRoleBinding":
            assert o["roleRef"]["name"] != "cluster-admin"


@pytest.mark.parametrize("namespace", ["default", "org-a"])
def test_service_account(namespace: str) -> None:
    assert ("ServiceAccount", namespace, "automation") in objects(["default", "org-a"])


@pytest.mark.parametrize(
    "namespaces, namespace, subjects",
    [
        # `default/automation` is cluster-admin in `default` by a RoleBinding only
        (["default"], "default", [sa("default")]),
        # an organisation's namespace binds both `automation` accounts
        (["default", "org-a"], "org-a", [sa("org-a"), sa("default")]),
        # the protected namespace drops `default/automation`
        (["default", "org-giantswarm"], "org-giantswarm", [sa("org-giantswarm")]),
    ],
)
def test_write_all(namespaces: list[str], namespace: str, subjects: list[dict]) -> None:
    rb = objects(namespaces)[("RoleBinding", namespace, "write-all-customer-sa")]
    assert rb["roleRef"] == ref("ClusterRole", "cluster-admin")
    assert rb["subjects"] == subjects


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
    "namespaces, existing, namespace, name, expected",
    [
        (
            ["default", "org-a"],
            {"default", "org-a", "kube-system"},
            "kube-system",
            "write-policy-exceptions",
            True,
        ),
        (
            ["default", "org-a"],
            {"default", "org-a", "kube-system"},
            "policy-exceptions",
            "write-policy-exceptions",
            False,
        ),
        (
            ["default", "org-a"],
            {"default", "org-a", "kube-system"},
            "giantswarm",
            "patch-charts",
            False,
        ),
        # without an organisation, nobody shares the Roles
        (["default"], None, "giantswarm", "patch-charts", False),
    ],
)
def test_shared_role_needs_its_namespace(
    namespaces: list[str],
    existing: set[str] | None,
    namespace: str,
    name: str,
    expected: bool,
) -> None:
    assert (
        ("RoleBinding", namespace, name) in objects(namespaces, existing)
    ) is expected


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


BINDING = {
    "kind": "RoleBinding",
    "roleRef": ref("ClusterRole", "view"),
    "subjects": [sa("a")],
}
ROLE = {
    "kind": "Role",
    "rules": [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get"]}],
}


@pytest.mark.parametrize(
    "existing, expected",
    [
        # what the API server adds, such as metadata, doesn't count
        ({**BINDING, "metadata": {"uid": "1"}}, False),
        ({**BINDING, "subjects": [sa("a"), sa("b")]}, True),
        ({**BINDING, "roleRef": ref("ClusterRole", "cluster-admin")}, True),
        (ROLE, True),
    ],
)
def test_needs_update_compares_rules_subjects_and_role_ref(
    existing: dict, expected: bool
) -> None:
    # as rbac-operator's CreateOrUpdate does, rather than leave a stale object as it is
    assert needs_update(BINDING, existing) is expected
