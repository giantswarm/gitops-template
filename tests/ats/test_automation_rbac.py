"""Checks of the bindings automation_rbac gives the `automation` ServiceAccounts; they need no
cluster."""

import pykube
from automation_rbac import automation_binding


def test_organization_automation_is_admin_of_its_namespace_only() -> None:
    binding = automation_binding(None, "org-a")
    assert isinstance(binding, pykube.RoleBinding)
    assert binding.obj["metadata"] == {
        "name": "write-all-customer-sa",
        "namespace": "org-a",
    }
    assert binding.obj["subjects"] == [
        {"kind": "ServiceAccount", "name": "automation", "namespace": "org-a"}
    ]
    assert binding.obj["roleRef"]["name"] == "cluster-admin"


def test_default_automation_is_cluster_admin() -> None:
    binding = automation_binding(None, "default")
    assert isinstance(binding, pykube.ClusterRoleBinding)
    assert binding.obj["metadata"] == {"name": "automation-cluster-admin-default"}
    assert binding.obj["subjects"][0]["namespace"] == "default"
