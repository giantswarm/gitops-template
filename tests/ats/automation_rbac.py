"""The `automation_rbac` fixture: it gives the `automation` ServiceAccounts the rights they have
on a Giant Swarm management cluster, so that an example a management cluster would refuse fails
here too. automation_bindings says which objects; the test's own setup keeps using the test's
admin client.
"""

import logging
from collections.abc import Iterator

import pykube
import pytest
from automation_bindings import automation_rbac_objects
from automation_roles import FLUX_APP, MC_BASES, RBAC_OPERATOR
from conftest import GitOpsTestConfig
from pytest_helm_charts.clusters import Cluster
from rbac_reconcile import create_or_update

OBJECT_KINDS: dict[str, type[pykube.objects.APIObject]] = {
    "ServiceAccount": pykube.ServiceAccount,
    "ClusterRole": pykube.ClusterRole,
    "ClusterRoleBinding": pykube.ClusterRoleBinding,
    "Role": pykube.Role,
    "RoleBinding": pykube.RoleBinding,
}

logger = logging.getLogger(__name__)


def get_json(api: pykube.HTTPClient, version: str) -> dict:
    # pykube asks /api/v1 for the core group and /apis/<group>/<version> for the others
    response = api.get(version=version)
    response.raise_for_status()
    return response.json()


def discover(api: pykube.HTTPClient) -> list[dict]:
    """The APIResourceLists of every group version the API server serves, the core group first
    and each group's preferred version first, as client-go's discovery lists them."""
    group_versions = ["v1"]
    for group in get_json(api, "/apis")["groups"]:
        preferred = group["preferredVersion"]["groupVersion"]
        others = [v["groupVersion"] for v in group["versions"]]
        group_versions += [preferred] + [v for v in others if v != preferred]
    return [get_json(api, group_version) for group_version in group_versions]


@pytest.fixture(scope="module")
def automation_rbac(
    kube_cluster: Cluster,
    gitops_test_config: GitOpsTestConfig,
    init_namespaces: None,
    kyverno: None,
    gs_crds: None,
    capi_crds: None,
    external_secrets: None,
    flux_app_deployment: None,
    workload_cluster_flux_crds: None,
) -> Iterator[None]:
    """Give `automation` its management-cluster rights, once every CRD of the test is installed.

    `read-all` covers the resources served when it's created, as rbac-operator's covers the ones
    served when it last reconciled. rbac_reconcile brings an object that exists already in line.
    The fixture deletes what it created, also when the setup fails part of the way.
    """
    api = kube_cluster.kube_client
    existing = {ns.name for ns in pykube.Namespace.objects(api)}
    objects = automation_rbac_objects(
        gitops_test_config.init_namespaces, existing, discover(api)
    )
    created = []
    try:
        for obj in objects:
            kube_obj = OBJECT_KINDS[obj["kind"]](api, obj)
            if create_or_update(kube_obj):
                created.append(kube_obj)
        logger.info(
            f"Gave `automation` the rights of a management cluster, from {RBAC_OPERATOR}, "
            f"{MC_BASES} and {FLUX_APP}: created {len(created)} objects"
        )
        yield None
    finally:
        for kube_obj in reversed(created):
            kube_obj.delete()
