"""Checks of the rights the kind test gives Kyverno's background controller, as rbac-operator
does on a management cluster; they need no cluster."""

from kyverno_generate_rbac import (
    CLUSTER_ROLE,
    cluster_role,
    org_namespaces,
    role_binding,
)


def test_cluster_role_is_rbac_operators() -> None:
    assert cluster_role() == {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": "write-kyverno-generated-externalsecrets"},
        "rules": [
            {
                "apiGroups": ["external-secrets.io"],
                "resources": ["externalsecrets", "secretstores"],
                "verbs": [
                    "get",
                    "list",
                    "watch",
                    "create",
                    "update",
                    "patch",
                    "delete",
                ],
            },
            {
                "apiGroups": [""],
                "resources": ["secrets"],
                "verbs": ["get", "list", "watch"],
            },
        ],
    }


def test_role_binding_binds_kyvernos_background_controller() -> None:
    assert role_binding("org-a") == {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": CLUSTER_ROLE, "namespace": "org-a"},
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": CLUSTER_ROLE,
        },
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": "kyverno-background-controller",
                "namespace": "kyverno",
            }
        ],
    }


def test_org_namespaces_leaves_out_the_others() -> None:
    assert org_namespaces(["default", "org-a", "giantswarm", "org-b"]) == [
        "org-a",
        "org-b",
    ]
