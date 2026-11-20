"""Which objects give the `automation` ServiceAccounts the rights they have on a Giant Swarm
management cluster.

Customer Kustomizations and HelmReleases run as `automation` (`spec.serviceAccountName`), the
ServiceAccount rbac-operator creates in `default` and in every `org-*` namespace. automation_roles
holds the rules, and automation_accounts what each account is bound to. The bindings are copied
from these sources; the comment of each says from where:

- giantswarm/rbac-operator at 4681152f3de2a062788baa7ecd44a2882acbce5d (RBAC_OPERATOR):
  service/controller/defaultnamespace/resource/automationsa/create.go (`default/automation`),
  service/controller/defaultnamespace/resource/fluxauth/create.go (the RoleBindingTemplate
  `write-all-customer-sa`, which service/controller/rolebindingtemplate/resource/rolebinding
  turns into a RoleBinding in every organisation namespace),
  service/controller/rbac/resource/automation/create.go (`org-*/automation` and the Roles the
  organisations share), pkg/key/key.go (the names);
- giantswarm/management-cluster-bases at 52aa8ee8a4ddb0c95e693bac67556150e33d956f
  (MC_BASES): bases/flux-app-v2/common/resource-rbac.yaml.

Left out: the ClusterRoleBinding to Crossplane's `crossplane-edit`, which rbac-operator creates
only where Crossplane runs, and the kind cluster runs no Crossplane; and the Roles of legacy
per-cluster namespaces, which Cluster API management clusters don't have.
"""

from automation_accounts import (
    DEFAULT_NAMESPACE,
    default_automation_objects,
    org_automation_objects,
)
from automation_roles import (
    PATCH_CHARTS_RULES,
    WRITE_POLICY_EXCEPTIONS_RULES,
    cluster_roles,
    read_all_rules,
)
from rbac_manifests import automation, role, role_binding, role_ref

# rbac-operator's org namespace test is the prefix: pkg/key/key.go IsOrgNamespace
ORG_NAMESPACE_PREFIX = "org-"
# pkg/key/key.go WritePolicyExceptionsNamespaces, lines 49-53
WRITE_POLICY_EXCEPTIONS_NAMESPACES = ["kube-system", "giantswarm", "policy-exceptions"]
# rbac/resource/automation/create.go lines 104-138
SHARED_ROLES = [("patch-charts", "giantswarm", PATCH_CHARTS_RULES)] + [
    ("write-policy-exceptions", ns, WRITE_POLICY_EXCEPTIONS_RULES)
    for ns in WRITE_POLICY_EXCEPTIONS_NAMESPACES
]


class NotAutomationNamespaceError(ValueError):
    """A namespace where a management cluster has no `automation` ServiceAccount."""

    def __init__(self, namespaces: list[str]) -> None:
        super().__init__(
            "rbac-operator creates `automation` only in `default` and the `org-*` "
            f"namespaces, not in {namespaces}"
        )


def shared_role_objects(orgs: list[str], existing_namespaces: set[str]) -> list[dict]:
    """The Roles every organisation's `automation` shares, with one RoleBinding listing them all.

    rbac-operator skips a namespace that doesn't exist for `write-policy-exceptions`; the test
    does that for `giantswarm` too, which every management cluster has.
    """
    subjects = [automation(ns) for ns in orgs]
    objects = []
    for name, namespace, rules in SHARED_ROLES:
        if orgs and namespace in existing_namespaces:
            ref = role_ref("Role", name)
            objects += [
                role(name, namespace, rules),
                role_binding(name, namespace, ref, subjects),
            ]
    return objects


def automation_rbac_objects(
    namespaces: list[str], existing_namespaces: set[str], discovery: list[dict]
) -> list[dict]:
    """Every object that gives the `automation` ServiceAccounts of `namespaces` their rights."""
    orgs = [ns for ns in namespaces if ns.startswith(ORG_NAMESPACE_PREFIX)]
    unknown = [ns for ns in namespaces if ns != DEFAULT_NAMESPACE and ns not in orgs]
    if unknown:
        raise NotAutomationNamespaceError(unknown)
    objects = cluster_roles(read_all_rules(discovery))
    objects += default_automation_objects(existing_namespaces)
    for ns in orgs:
        objects += org_automation_objects(ns)
    return objects + shared_role_objects(orgs, existing_namespaces)
