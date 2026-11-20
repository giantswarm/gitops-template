"""Checks of the replica of rbac-operator's RBAC for the `automation` ServiceAccounts; they need
no cluster."""

import pytest
from automation_rbac import automation_rbac_objects
from automation_roles import read_all_rules

CORE = {
    "groupVersion": "v1",
    "resources": [
        {"name": "pods", "verbs": ["get", "list"]},
        {"name": "pods/log", "verbs": ["get"]},
        {"name": "configmaps", "verbs": ["get"]},
        {"name": "secrets", "verbs": ["get"]},
        {"name": "bindings", "verbs": []},
        {"name": "namespaces", "verbs": ["get"]},
    ],
}
APPS_V1 = {
    "groupVersion": "apps/v1",
    "resources": [{"name": "deployments", "verbs": ["get"]}],
}
EXAMPLE_V2 = {
    "groupVersion": "example.io/v2",
    "resources": [{"name": "widgets", "verbs": ["get"]}],
}
EXAMPLE_V1 = {
    "groupVersion": "example.io/v1",
    "resources": [
        {"name": "widgets", "verbs": ["get"]},
        {"name": "gadgets", "verbs": ["get"]},
    ],
}

READ = ["get", "list", "watch"]


def by_kind_and_name(objects: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {
        (o["kind"], o["metadata"].get("namespace", ""), o["metadata"]["name"]): o
        for o in objects
    }


def sa(namespace: str) -> dict:
    return {"kind": "ServiceAccount", "name": "automation", "namespace": namespace}


def objects(namespaces: list[str], existing: set[str] | None = None) -> dict:
    if existing is None:
        existing = {"default", "giantswarm", "kube-system", *namespaces}
    return by_kind_and_name(
        automation_rbac_objects(namespaces, existing, [CORE, APPS_V1])
    )


def test_read_all_rules_skips_configmaps_secrets_subresources_and_verbless() -> None:
    assert read_all_rules([CORE, APPS_V1]) == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": READ},
        {"apiGroups": [""], "resources": ["namespaces"], "verbs": READ},
        {"apiGroups": ["apps"], "resources": ["deployments"], "verbs": READ},
        {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]},
    ]


def test_read_all_rules_have_one_rule_per_resource_across_versions() -> None:
    assert read_all_rules([EXAMPLE_V2, EXAMPLE_V1]) == [
        {"apiGroups": ["example.io"], "resources": ["widgets"], "verbs": READ},
        {"apiGroups": ["example.io"], "resources": ["gadgets"], "verbs": READ},
        {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]},
    ]


def test_no_cluster_admin_cluster_role_binding() -> None:
    for (kind, _, _), o in objects(["default", "org-a"]).items():
        if kind == "ClusterRoleBinding":
            assert o["roleRef"]["name"] != "cluster-admin"


def test_service_accounts_in_default_and_org_namespaces() -> None:
    got = objects(["default", "org-a"])
    assert ("ServiceAccount", "default", "automation") in got
    assert ("ServiceAccount", "org-a", "automation") in got


def test_default_automation_cluster_role_bindings() -> None:
    got = objects(["default", "org-a"])
    for name, role in [
        ("read-all-customer-sa", "read-all"),
        ("write-organizations-customer-sa", "write-organizations"),
        ("write-client-certificates-customer-sa", "write-client-certificates"),
        ("write-silences-customer-sa", "write-silences"),
        ("write-policy-exceptions-customer-sa", "write-policy-exceptions"),
        (
            "write-aws-cluster-role-identity-customer-sa",
            "write-aws-cluster-role-identity",
        ),
    ]:
        crb = got[("ClusterRoleBinding", "", name)]
        assert crb["roleRef"] == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": role,
        }
        assert crb["subjects"] == [sa("default")]


def test_default_automation_is_cluster_admin_in_default_only_by_role_binding() -> None:
    rb = objects(["default"])[("RoleBinding", "default", "write-all-customer-sa")]
    assert rb["roleRef"]["name"] == "cluster-admin"
    assert rb["subjects"] == [sa("default")]


def test_org_namespace_write_all_binds_both_automation_accounts() -> None:
    rb = objects(["default", "org-a"])[
        ("RoleBinding", "org-a", "write-all-customer-sa")
    ]
    assert rb["roleRef"]["name"] == "cluster-admin"
    assert rb["subjects"] == [sa("org-a"), sa("default")]


def test_protected_org_namespace_drops_default_automation() -> None:
    rb = objects(["default", "org-giantswarm"])[
        ("RoleBinding", "org-giantswarm", "write-all-customer-sa")
    ]
    assert rb["subjects"] == [sa("org-giantswarm")]


def test_org_automation_cluster_role_bindings() -> None:
    got = objects(["default", "org-a"])
    for role in [
        "write-silences",
        "kamaji-datastore-manager",
        "cluster-app-chart-lookups",
    ]:
        crb = got[("ClusterRoleBinding", "", f"{role}-customer-sa-ns-org-a")]
        assert crb["roleRef"]["name"] == role
        assert crb["subjects"] == [sa("org-a")]


def test_org_automation_has_no_read_all() -> None:
    got = objects(["default", "org-a"])
    for (kind, _, _), o in got.items():
        if kind == "ClusterRoleBinding" and o["roleRef"]["name"] == "read-all":
            assert sa("org-a") not in o["subjects"]


def test_shared_roles_list_every_org_automation_account() -> None:
    got = objects(["default", "org-a", "org-b"])
    for namespace, name in [
        ("giantswarm", "patch-charts"),
        ("giantswarm", "write-policy-exceptions"),
        ("kube-system", "write-policy-exceptions"),
    ]:
        assert ("Role", namespace, name) in got
        rb = got[("RoleBinding", namespace, name)]
        assert rb["roleRef"] == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": name,
        }
        assert rb["subjects"] == [sa("org-a"), sa("org-b")]


def test_shared_roles_skip_missing_namespaces() -> None:
    got = objects(["default", "org-a"], {"default", "org-a", "kube-system"})
    assert ("RoleBinding", "kube-system", "write-policy-exceptions") in got
    assert ("RoleBinding", "policy-exceptions", "write-policy-exceptions") not in got
    assert ("RoleBinding", "giantswarm", "patch-charts") not in got


def test_no_shared_roles_without_org_namespaces() -> None:
    got = objects(["default"])
    assert ("RoleBinding", "giantswarm", "patch-charts") not in got


def test_cluster_roles_are_copied() -> None:
    got = objects(["default", "org-a"])
    assert got[("ClusterRole", "", "write-organizations")]["rules"] == [
        {
            "apiGroups": ["security.giantswarm.io"],
            "resources": ["organizations"],
            "verbs": ["*"],
        }
    ]
    assert got[("ClusterRole", "", "read-all")]["rules"] == read_all_rules(
        [CORE, APPS_V1]
    )
    assert ("ClusterRole", "", "kamaji-datastore-manager") not in got


def test_flux_app_bindings_of_default_automation() -> None:
    got = objects(["default"], {"default", "flux-giantswarm"})
    rb = got[("RoleBinding", "default", "flux-crd-controller")]
    assert rb["roleRef"]["name"] == "crd-controller-giantswarm"
    assert rb["subjects"] == [sa("default")]
    assert ("ClusterRole", "", "crd-controller-giantswarm") in got
    logs = got[("RoleBinding", "flux-giantswarm", "read-flux-logs-automation")]
    assert logs["subjects"] == [sa("default")]


def test_namespaces_other_than_default_and_org_are_refused() -> None:
    # rbac-operator creates `automation` in `default` and the `org-*` namespaces only
    with pytest.raises(ValueError, match="team-a"):
        automation_rbac_objects(["default", "team-a"], {"default"}, [CORE])
