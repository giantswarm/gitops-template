"""The rights Kyverno's background controller has in every organisation's namespace on a Giant
Swarm management cluster, where rbac-operator creates them.

The Kyverno Policy in organizations/ORG_NAME/workload-cluster-secret-stores generates
ExternalSecrets and SecretStores and reads kubeconfig Secrets in the organisation's namespace,
and Kyverno rejects the Policy unless its background controller may. The example doesn't grant
that: rbac-operator binds the ClusterRole `write-kyverno-generated-externalsecrets` to
`kyverno/kyverno-background-controller` with a RoleBinding in every `org-*` namespace. The
`kyverno_generate_rbac` fixture mirrors those objects in the test cluster before Flux applies
the repository. It stands on its own, so it can move into a full replica of rbac-operator's
rights.
"""

from collections.abc import Iterable, Iterator

import pykube
import pytest
from conftest import GitOpsTestConfig, apply
from pytest_helm_charts.clusters import Cluster

CLUSTER_ROLE = "write-kyverno-generated-externalsecrets"
RBAC_API = "rbac.authorization.k8s.io"
KYVERNO_BACKGROUND_CONTROLLER = {
    "kind": "ServiceAccount",
    "name": "kyverno-background-controller",
    "namespace": "kyverno",
}


def cluster_role() -> dict:
    """rbac-operator's ClusterRole for what Kyverno generates in an organisation's namespace."""
    return {
        "apiVersion": f"{RBAC_API}/v1",
        "kind": "ClusterRole",
        "metadata": {"name": CLUSTER_ROLE},
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


def role_binding(namespace: str) -> dict:
    """rbac-operator's RoleBinding of CLUSTER_ROLE to Kyverno's background controller in the
    organisation's `namespace`."""
    return {
        "apiVersion": f"{RBAC_API}/v1",
        "kind": "RoleBinding",
        "metadata": {"name": CLUSTER_ROLE, "namespace": namespace},
        "roleRef": {"apiGroup": RBAC_API, "kind": "ClusterRole", "name": CLUSTER_ROLE},
        "subjects": [KYVERNO_BACKGROUND_CONTROLLER],
    }


def org_namespaces(namespaces: Iterable[str]) -> list[str]:
    """The organisations' namespaces among `namespaces`."""
    return [ns for ns in namespaces if ns.startswith("org-")]


@pytest.fixture(scope="module")
def kyverno_generate_rbac(
    kube_cluster: Cluster, init_namespaces: None, gitops_test_config: GitOpsTestConfig
) -> Iterator[None]:
    """Create rbac-operator's ClusterRole and its RoleBinding in every organisation's namespace."""
    api = kube_cluster.kube_client
    created = [apply(pykube.ClusterRole(api, cluster_role()))]
    created += [
        apply(pykube.RoleBinding(api, role_binding(ns)))
        for ns in org_namespaces(gitops_test_config.init_namespaces)
    ]
    yield
    for obj in reversed(created):
        obj.delete()
