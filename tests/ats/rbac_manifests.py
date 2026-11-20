"""The manifests of the ServiceAccounts, Roles, ClusterRoles and bindings that replicate
rbac-operator's RBAC for the `automation` ServiceAccounts, labelled as rbac-operator labels them.
"""

AUTOMATION = "automation"
MANAGED_BY = {"giantswarm.io/managed-by": "rbac-operator"}
RBAC_V1 = "rbac.authorization.k8s.io/v1"


def metadata(name: str, namespace: str | None = None) -> dict:
    meta = {"name": name, "labels": MANAGED_BY}
    if namespace is not None:
        meta["namespace"] = namespace
    return meta


def automation(namespace: str) -> dict:
    """The `automation` ServiceAccount of `namespace` as the subject of a binding."""
    return {"kind": "ServiceAccount", "name": AUTOMATION, "namespace": namespace}


def service_account(namespace: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": metadata(AUTOMATION, namespace),
    }


def role_ref(kind: str, name: str) -> dict:
    return {"apiGroup": "rbac.authorization.k8s.io", "kind": kind, "name": name}


def cluster_role(name: str, rules: list[dict]) -> dict:
    return {
        "apiVersion": RBAC_V1,
        "kind": "ClusterRole",
        "metadata": metadata(name),
        "rules": rules,
    }


def role(name: str, namespace: str, rules: list[dict]) -> dict:
    return {
        "apiVersion": RBAC_V1,
        "kind": "Role",
        "metadata": metadata(name, namespace),
        "rules": rules,
    }


def cluster_role_binding(
    name: str, cluster_role_name: str, subjects: list[dict]
) -> dict:
    return {
        "apiVersion": RBAC_V1,
        "kind": "ClusterRoleBinding",
        "metadata": metadata(name),
        "roleRef": role_ref("ClusterRole", cluster_role_name),
        "subjects": subjects,
    }


def role_binding(name: str, namespace: str, ref: dict, subjects: list[dict]) -> dict:
    return {
        "apiVersion": RBAC_V1,
        "kind": "RoleBinding",
        "metadata": metadata(name, namespace),
        "roleRef": ref,
        "subjects": subjects,
    }
