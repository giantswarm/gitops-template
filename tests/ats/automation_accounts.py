"""What each `automation` ServiceAccount of a Giant Swarm management cluster is bound to:
`default/automation`, with what Giant Swarm's Flux gives it, and the `automation` of an
organisation namespace. automation_bindings plans them, with the Roles the organisations share,
and names the sources of the line numbers below.
"""

from automation_roles import READ_PODS_AND_LOGS_RULES
from rbac_manifests import automation, cluster_role_binding, role, role_binding
from rbac_manifests import role_ref, service_account

DEFAULT_NAMESPACE = "default"
# a RoleBinding from a RoleBindingTemplate in it keeps only subjects of its own namespace and
#  flux-system: rolebindingtemplate/resource/rolebinding/create.go cleanSubjects
PROTECTED_NAMESPACE = "org-giantswarm"
GIANTSWARM_FLUX_NAMESPACE = "flux-giantswarm"
CLUSTER_ADMIN = role_ref("ClusterRole", "cluster-admin")
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
        ns, logs = GIANTSWARM_FLUX_NAMESPACE, "read-pods-and-logs"
        objects += [
            role(logs, ns, READ_PODS_AND_LOGS_RULES),
            role_binding(
                "read-flux-logs-automation", ns, role_ref("Role", logs), subject
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
            "write-all-customer-sa", DEFAULT_NAMESPACE, CLUSTER_ADMIN, subject
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
            "write-all-customer-sa", namespace, CLUSTER_ADMIN, write_all_subjects
        ),
    ]
