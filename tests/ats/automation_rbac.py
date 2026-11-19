"""The rights of the `automation` ServiceAccounts in the test cluster, as rbac-operator grants
them on a Giant Swarm management cluster.

- `default/automation`, which the management cluster's Kustomization runs as, is
  cluster-admin.
- `org-<org>/automation`, which the organization's Kustomizations run as, is cluster-admin in
  its own namespace only: rbac-operator binds it there with the `write-all-customer-sa`
  RoleBinding. rbac-operator also gives it a few cluster-wide read rights the cluster charts
  need when they render on a management cluster; nothing in the test needs them.
"""

import pykube
from pykube.objects import APIObject

SERVICE_ACCOUNT_NAME = "automation"
ORGANIZATION_PREFIX = "org-"
# rbac-operator's name for the RoleBinding of an organization's `automation`
ORGANIZATION_ROLE_BINDING_NAME = "write-all-customer-sa"


def automation_binding(api: pykube.HTTPClient | None, namespace: str) -> APIObject:
    """The binding that gives `<namespace>/automation` its rights: a RoleBinding in an
    organization namespace, a ClusterRoleBinding anywhere else."""
    spec = {
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": "cluster-admin",
        },
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": SERVICE_ACCOUNT_NAME,
                "namespace": namespace,
            }
        ],
    }
    if namespace.startswith(ORGANIZATION_PREFIX):
        metadata = {"name": ORGANIZATION_ROLE_BINDING_NAME, "namespace": namespace}
        return pykube.RoleBinding(api, {"metadata": metadata, **spec})
    metadata = {"name": f"{SERVICE_ACCOUNT_NAME}-cluster-admin-{namespace}"}
    return pykube.ClusterRoleBinding(api, {"metadata": metadata, **spec})
