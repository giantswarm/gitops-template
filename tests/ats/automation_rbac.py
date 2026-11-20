"""The rights of the `automation` ServiceAccounts, as on a Giant Swarm management cluster.

Customer Kustomizations and HelmReleases run as `automation` (`spec.serviceAccountName`), the
ServiceAccount rbac-operator creates in `default` and in every `org-*` namespace. The test gives
them exactly the Roles, ClusterRoles and bindings a management cluster gives them, so an example
that a management cluster would refuse fails here too. The test's own setup keeps using the
test's admin client.

automation_roles holds the rules. The bindings are copied from these sources; the comment of
each says from where:

- giantswarm/rbac-operator at 4681152f3de2a062788baa7ecd44a2882acbce5d (RBAC_OPERATOR):
  service/controller/defaultnamespace/resource/automationsa/create.go (`default/automation`),
  service/controller/defaultnamespace/resource/fluxauth/create.go (the RoleBindingTemplate
  `write-all-customer-sa`, which service/controller/rolebindingtemplate/resource/rolebinding
  turns into a RoleBinding in every organization namespace),
  service/controller/rbac/resource/automation/create.go (`org-*/automation`),
  pkg/key/key.go (the names);
- giantswarm/management-cluster-bases at 52aa8ee8a4ddb0c95e693bac67556150e33d956f
  (MC_BASES): bases/flux-app-v2/common/resource-rbac.yaml.

Left out: the ClusterRoleBinding to Crossplane's `crossplane-edit`, which rbac-operator creates
only where Crossplane runs, and the kind cluster runs no Crossplane; and the Roles of legacy
per-cluster namespaces, which Cluster API management clusters don't have.
"""

import logging
from collections.abc import Iterator

import pykube
import pytest
from automation_roles import (
    FLUX_APP,
    MANAGED_BY,
    MC_BASES,
    PATCH_CHARTS_RULES,
    RBAC_OPERATOR,
    READ_PODS_AND_LOGS_RULES,
    WRITE_POLICY_EXCEPTIONS_RULES,
    cluster_roles,
    read_all_rules,
    role,
)
from conftest import GitOpsTestConfig
from pytest_helm_charts.clusters import Cluster

AUTOMATION = "automation"
DEFAULT_NAMESPACE = "default"
# rbac-operator's org namespace test is the prefix: pkg/key/key.go IsOrgNamespace
ORG_NAMESPACE_PREFIX = "org-"
# a RoleBinding from a RoleBindingTemplate in it keeps only subjects of its own namespace and
#  flux-system: rolebindingtemplate/resource/rolebinding/create.go cleanSubjects
PROTECTED_NAMESPACE = "org-giantswarm"
GIANTSWARM_FLUX_NAMESPACE = "flux-giantswarm"
# pkg/key/key.go WritePolicyExceptionsNamespaces, lines 49-53
WRITE_POLICY_EXCEPTIONS_NAMESPACES = ["kube-system", "giantswarm", "policy-exceptions"]
# rbac/resource/automation/create.go lines 104-138
SHARED_ROLES = [("patch-charts", "giantswarm", PATCH_CHARTS_RULES)] + [
    ("write-policy-exceptions", ns, WRITE_POLICY_EXCEPTIONS_RULES)
    for ns in WRITE_POLICY_EXCEPTIONS_NAMESPACES
]
# automationsa/create.go lines 159-322: `<role>-customer-sa`; the last one on CAPA only
DEFAULT_AUTOMATION_CLUSTER_ROLES = [
    "write-organizations",
    "write-client-certificates",
    "write-silences",
    "write-policy-exceptions",
    "write-aws-cluster-role-identity",
]
# rbac/resource/automation/create.go lines 67-102: `<role>-customer-sa-ns-<namespace>`
ORG_AUTOMATION_CLUSTER_ROLES = [
    "write-silences",
    "kamaji-datastore-manager",
    "cluster-app-chart-lookups",
]

logger = logging.getLogger(__name__)


class NotAutomationNamespaceError(ValueError):
    """A namespace where a management cluster has no `automation` ServiceAccount."""

    def __init__(self, namespaces: list[str]) -> None:
        super().__init__(
            "rbac-operator creates `automation` only in `default` and the `org-*` "
            f"namespaces, not in {namespaces}"
        )


def automation(namespace: str) -> dict:
    return {"kind": "ServiceAccount", "name": AUTOMATION, "namespace": namespace}


def service_account(namespace: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": AUTOMATION, "namespace": namespace, "labels": MANAGED_BY},
    }


def role_ref(kind: str, name: str) -> dict:
    return {"apiGroup": "rbac.authorization.k8s.io", "kind": kind, "name": name}


def cluster_role_binding(name: str, cluster_role: str, subjects: list[dict]) -> dict:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": name, "labels": MANAGED_BY},
        "roleRef": role_ref("ClusterRole", cluster_role),
        "subjects": subjects,
    }


def role_binding(name: str, namespace: str, ref: dict, subjects: list[dict]) -> dict:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": name, "namespace": namespace, "labels": MANAGED_BY},
        "roleRef": ref,
        "subjects": subjects,
    }


def flux_objects(existing_namespaces: set[str]) -> list[dict]:
    """What MC_BASES resource-rbac.yaml gives `default/automation`."""
    subject = [automation(DEFAULT_NAMESPACE)]
    # lines 1-13: within `default`, where cluster-admin covers it
    objects = [
        role_binding(
            "flux-crd-controller",
            DEFAULT_NAMESPACE,
            role_ref("ClusterRole", "crd-controller-giantswarm"),
            subject,
        )
    ]
    # lines 34-61: in Giant Swarm's Flux namespace, which the kind cluster lacks; read-all
    #  covers it anyway
    if GIANTSWARM_FLUX_NAMESPACE in existing_namespaces:
        objects += [
            role(
                "read-pods-and-logs",
                GIANTSWARM_FLUX_NAMESPACE,
                READ_PODS_AND_LOGS_RULES,
            ),
            role_binding(
                "read-flux-logs-automation",
                GIANTSWARM_FLUX_NAMESPACE,
                role_ref("Role", "read-pods-and-logs"),
                subject,
            ),
        ]
    return objects


def default_automation_objects(existing_namespaces: set[str]) -> list[dict]:
    """`default/automation`: automationsa/create.go EnsureCreated, lines 22-75."""
    subject = [automation(DEFAULT_NAMESPACE)]
    return [
        service_account(DEFAULT_NAMESPACE),
        # lines 94-123
        cluster_role_binding("read-all-customer-sa", "read-all", subject),
        # lines 128-157: cluster-admin, but in `default` only
        role_binding(
            "write-all-customer-sa",
            DEFAULT_NAMESPACE,
            role_ref("ClusterRole", "cluster-admin"),
            subject,
        ),
        *(
            cluster_role_binding(f"{name}-customer-sa", name, subject)
            for name in DEFAULT_AUTOMATION_CLUSTER_ROLES
        ),
        *flux_objects(existing_namespaces),
    ]


def org_automation_objects(namespace: str) -> list[dict]:
    """`org-*/automation`: rbac/resource/automation/create.go EnsureCreated, lines 37-102, and
    the RoleBinding of the RoleBindingTemplate `write-all-customer-sa` in the namespace.
    """
    subject = [automation(namespace)]
    # fluxauth/create.go lines 36-74: the subject without a namespace gets the RoleBinding's
    #  (rolebinding/create.go lines 99-108); the protected namespace drops `default/automation`
    write_all_subjects = [automation(namespace)]
    if namespace != PROTECTED_NAMESPACE:
        write_all_subjects.append(automation(DEFAULT_NAMESPACE))
    return [
        service_account(namespace),
        *(
            cluster_role_binding(f"{name}-customer-sa-ns-{namespace}", name, subject)
            for name in ORG_AUTOMATION_CLUSTER_ROLES
        ),
        role_binding(
            "write-all-customer-sa",
            namespace,
            role_ref("ClusterRole", "cluster-admin"),
            write_all_subjects,
        ),
    ]


def shared_role_objects(
    org_namespaces: list[str], existing_namespaces: set[str]
) -> list[dict]:
    """The Roles every organization's `automation` shares, with one RoleBinding listing them all.

    rbac-operator skips a namespace that doesn't exist for `write-policy-exceptions`; the test
    does that for `giantswarm` too, which every management cluster has.
    """
    if not org_namespaces:
        return []
    subjects = [automation(ns) for ns in org_namespaces]
    objects = []
    for name, namespace, rules in SHARED_ROLES:
        if namespace in existing_namespaces:
            objects += [
                role(name, namespace, rules),
                role_binding(name, namespace, role_ref("Role", name), subjects),
            ]
    return objects


def automation_rbac_objects(
    namespaces: list[str], existing_namespaces: set[str], discovery: list[dict]
) -> list[dict]:
    """Every object that gives the `automation` ServiceAccounts of `namespaces` their rights."""
    org_namespaces = [ns for ns in namespaces if ns.startswith(ORG_NAMESPACE_PREFIX)]
    unknown = [
        ns for ns in namespaces if ns != DEFAULT_NAMESPACE and ns not in org_namespaces
    ]
    if unknown:
        raise NotAutomationNamespaceError(unknown)
    objects = cluster_roles(read_all_rules(discovery))
    objects += default_automation_objects(existing_namespaces)
    for ns in org_namespaces:
        objects += org_automation_objects(ns)
    objects += shared_role_objects(org_namespaces, existing_namespaces)
    return objects


def discover(api: pykube.HTTPClient) -> list[dict]:
    """The APIResourceLists of every group version the API server serves, the core group first
    and each group's preferred version first, as client-go's discovery lists them."""
    group_versions = ["v1"]
    response = api.get(version="/apis")
    response.raise_for_status()
    for group in response.json()["groups"]:
        preferred = group["preferredVersion"]["groupVersion"]
        group_versions.append(preferred)
        group_versions += [
            v["groupVersion"]
            for v in group["versions"]
            if v["groupVersion"] != preferred
        ]
    lists = []
    for group_version in group_versions:
        # pykube asks /api/v1 for the core group and /apis/<group>/<version> for the others
        response = api.get(version=group_version)
        response.raise_for_status()
        lists.append(response.json())
    return lists


OBJECT_KINDS: dict[str, type[pykube.objects.APIObject]] = {
    "ServiceAccount": pykube.ServiceAccount,
    "ClusterRole": pykube.ClusterRole,
    "ClusterRoleBinding": pykube.ClusterRoleBinding,
    "Role": pykube.Role,
    "RoleBinding": pykube.RoleBinding,
}


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
    served when it last reconciled. Objects that exist already are left as they are; the
    fixture deletes only what it created.
    """
    api = kube_cluster.kube_client
    existing = {ns.name for ns in pykube.Namespace.objects(api)}
    objects = automation_rbac_objects(
        gitops_test_config.init_namespaces, existing, discover(api)
    )
    created = []
    for obj in objects:
        kube_obj = OBJECT_KINDS[obj["kind"]](api, obj)
        if not kube_obj.exists():
            kube_obj.create()
            created.append(kube_obj)
    logger.info(
        f"Gave `automation` the rights of a management cluster, from {RBAC_OPERATOR}, "
        f"{MC_BASES} and {FLUX_APP}: created {len(created)} objects"
    )

    yield None

    for kube_obj in reversed(created):
        kube_obj.delete()
