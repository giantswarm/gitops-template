"""The `automation_rbac` fixture: it gives the `automation` ServiceAccounts the rights they have
on a Giant Swarm management cluster, so that an example a management cluster would refuse fails
here too. automation_bindings says which objects; the test's own setup keeps using the test's
admin client.
"""

import json
import logging
from collections.abc import Iterator

import pykube
import pytest
from automation_bindings import automation_rbac_objects
from automation_roles import FLUX_APP, MC_BASES, RBAC_OPERATOR
from conftest import GitOpsTestConfig
from pytest_helm_charts.clusters import Cluster

# what rbac-operator's CreateOrUpdate compares (pkg/rbac): the rules of a Role or ClusterRole
#  and the subjects of a binding; the roleRef too, which the API server doesn't let it change
CONTENT_KEYS = ("rules", "subjects", "roleRef")

OBJECT_KINDS: dict[str, type[pykube.objects.APIObject]] = {
    "ServiceAccount": pykube.ServiceAccount,
    "ClusterRole": pykube.ClusterRole,
    "ClusterRoleBinding": pykube.ClusterRoleBinding,
    "Role": pykube.Role,
    "RoleBinding": pykube.RoleBinding,
}

logger = logging.getLogger(__name__)


def discover(api: pykube.HTTPClient) -> list[dict]:
    """The APIResourceLists of every group version the API server serves, the core group first
    and each group's preferred version first, as client-go's discovery lists them."""
    group_versions = ["v1"]
    response = api.get(version="/apis")
    response.raise_for_status()
    for group in response.json()["groups"]:
        preferred = group["preferredVersion"]["groupVersion"]
        others = [v["groupVersion"] for v in group["versions"]]
        group_versions += [preferred] + [v for v in others if v != preferred]
    lists = []
    for group_version in group_versions:
        # pykube asks /api/v1 for the core group and /apis/<group>/<version> for the others
        response = api.get(version=group_version)
        response.raise_for_status()
        lists.append(response.json())
    return lists


def needs_update(desired: dict, existing: dict) -> bool:
    return any(desired.get(key) != existing.get(key) for key in CONTENT_KEYS)


def create_or_update(
    api: pykube.HTTPClient, obj: dict
) -> pykube.objects.APIObject | None:
    """Create `obj`, or replace the object of its name if that differs, as rbac-operator does;
    the created object, or None when it existed."""
    kube_obj = OBJECT_KINDS[obj["kind"]](api, obj)
    response = api.get(**kube_obj.api_kwargs())
    if response.status_code == 404:
        kube_obj.create()
        return kube_obj
    api.raise_for_status(response)
    if needs_update(obj, response.json()):
        logger.info(
            f"Replacing {obj['kind']} {kube_obj.namespace or ''}/{kube_obj.name}"
        )
        api.raise_for_status(api.put(**kube_obj.api_kwargs(data=json.dumps(obj))))
    return None


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
    served when it last reconciled. An object that exists already is replaced when its rules,
    subjects or roleRef differ. The fixture deletes what it created, also when the setup fails
    part of the way.
    """
    api = kube_cluster.kube_client
    existing = {ns.name for ns in pykube.Namespace.objects(api)}
    objects = automation_rbac_objects(
        gitops_test_config.init_namespaces, existing, discover(api)
    )
    created = []
    try:
        for obj in objects:
            kube_obj = create_or_update(api, obj)
            if kube_obj is not None:
                created.append(kube_obj)
        logger.info(
            f"Gave `automation` the rights of a management cluster, from {RBAC_OPERATOR}, "
            f"{MC_BASES} and {FLUX_APP}: created {len(created)} objects"
        )
        yield None
    finally:
        for kube_obj in reversed(created):
            kube_obj.delete()
