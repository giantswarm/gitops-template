"""Which objects give the `automation` ServiceAccounts the rights they have on a Giant Swarm
management cluster.

Customer Kustomizations and HelmReleases run as `automation` (`spec.serviceAccountName`), the
ServiceAccount rbac-operator creates in `default` and in every `org-*` namespace. automation_roles
holds the rules. The bindings are copied from these sources; the comment of each says from where:

- giantswarm/rbac-operator at 4681152f3de2a062788baa7ecd44a2882acbce5d (RBAC_OPERATOR):
  service/controller/defaultnamespace/resource/automationsa/create.go (`default/automation`),
  service/controller/defaultnamespace/resource/fluxauth/create.go (the RoleBindingTemplate
  `write-all-customer-sa`, which service/controller/rolebindingtemplate/resource/rolebinding
  turns into a RoleBinding in every organisation namespace),
  service/controller/rbac/resource/automation/create.go (`org-*/automation`),
  pkg/key/key.go (the names);
- giantswarm/management-cluster-bases at 52aa8ee8a4ddb0c95e693bac67556150e33d956f
  (MC_BASES): bases/flux-app-v2/common/resource-rbac.yaml.

Left out: the ClusterRoleBinding to Crossplane's `crossplane-edit`, which rbac-operator creates
only where Crossplane runs, and the kind cluster runs no Crossplane; and the Roles of legacy
per-cluster namespaces, which Cluster API management clusters don't have.
"""

from automation_roles import (
    PATCH_CHARTS_RULES,
    READ_PODS_AND_LOGS_RULES,
    WRITE_POLICY_EXCEPTIONS_RULES,
    cluster_roles,
    read_all_rules,
)
from rbac_manifests import (
    automation,
    cluster_role_binding,
    role,
    role_binding,
    role_ref,
    service_account,
)

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


class NotAutomationNamespaceError(ValueError):
    """A namespace where a management cluster has no `automation` ServiceAccount."""

    def __init__(self, namespaces: list[str]) -> None:
        super().__init__(
            "rbac-operator creates `automation` only in `default` and the `org-*` "
            f"namespaces, not in {namespaces}"
        )


def flux_objects(existing_namespaces: set[str]) -> list[dict]:
    """What MC_BASES resource-rbac.yaml gives `default/automation`."""
    subject = [automation(DEFAULT_NAMESPACE)]
    # lines 1-13: within `default`, where cluster-admin covers it
    crd_controller = role_ref("ClusterRole", "crd-controller-giantswarm")
    objects = [
        role_binding("flux-crd-controller", DEFAULT_NAMESPACE, crd_controller, subject)
    ]
    # lines 34-61: in Giant Swarm's Flux namespace, which the kind cluster lacks; read-all
    #  covers it anyway
    if GIANTSWARM_FLUX_NAMESPACE in existing_namespaces:
        logs = role_ref("Role", "read-pods-and-logs")
        objects += [
            role(
                "read-pods-and-logs",
                GIANTSWARM_FLUX_NAMESPACE,
                READ_PODS_AND_LOGS_RULES,
            ),
            role_binding(
                "read-flux-logs-automation", GIANTSWARM_FLUX_NAMESPACE, logs, subject
            ),
        ]
    return objects


def default_automation_objects(existing_namespaces: set[str]) -> list[dict]:
    """`default/automation`: automationsa/create.go EnsureCreated, lines 22-75."""
    subject = [automation(DEFAULT_NAMESPACE)]
    cluster_admin = role_ref("ClusterRole", "cluster-admin")
    return [
        service_account(DEFAULT_NAMESPACE),
        # lines 94-123
        cluster_role_binding("read-all-customer-sa", "read-all", subject),
        # lines 128-157: cluster-admin, but in `default` only
        role_binding(
            "write-all-customer-sa", DEFAULT_NAMESPACE, cluster_admin, subject
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
    cluster_admin = role_ref("ClusterRole", "cluster-admin")
    return [
        service_account(namespace),
        *(
            cluster_role_binding(f"{name}-customer-sa-ns-{namespace}", name, subject)
            for name in ORG_AUTOMATION_CLUSTER_ROLES
        ),
        role_binding(
            "write-all-customer-sa", namespace, cluster_admin, write_all_subjects
        ),
    ]


def shared_role_objects(
    org_namespaces: list[str], existing_namespaces: set[str]
) -> list[dict]:
    """The Roles every organisation's `automation` shares, with one RoleBinding listing them all.

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
