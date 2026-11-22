"""The rights Kyverno's background controller needs on a Giant Swarm management cluster so that
a Kyverno NamespacedGeneratingPolicy in an organisation namespace can generate ExternalSecrets and
SecretStores from the Secrets that trigger it, such as the example in
organizations/ORG_NAME/multicluster/secret-stores.

Neither is released yet. The ClusterRole `write-kyverno-generated-externalsecrets` and its
RoleBinding in each organisation namespace are copied from giantswarm/rbac-operator pull request
829 at 80aed29e11e49eac3a7f77b601c6df124e66cfe4 (SOURCE):
service/controller/defaultnamespace/resource/clusterroles/create.go
createWriteKyvernoGeneratedExternalSecretsClusterRole (the ClusterRole),
service/controller/rbac/resource/automation/create.go EnsureCreated (the RoleBinding in each
organisation namespace) and pkg/key/key.go (the names).

That pull request doesn't grant the second, `list-kyverno-generating-policy-triggers`: `list` on
Secrets across the whole cluster. Kyverno 1.19.2 lists the triggers of a
NamespacedGeneratingPolicy in every namespace and only then keeps those in the policy's own
(KYVERNO_TRIGGER_LIST), when the policy is created, for `generateExisting`, and when the background
controller starts again, to find what it generated before. A RoleBinding can't grant a list across
the whole cluster. The name is the test's own.

automation_bindings plans them with the `automation` ServiceAccounts' objects.
"""

from automation_roles import READ, WRITE, rule
from rbac_manifests import cluster_role, cluster_role_binding, role_binding, role_ref

SOURCE = "giantswarm/rbac-operator@80aed29e11e49eac3a7f77b601c6df124e66cfe4"
KYVERNO_TRIGGER_LIST = "kyverno/kyverno@v1.19.2 pkg/policy/gpol.go getGpolTriggers"
NAMESPACE = "kyverno"
SERVICE_ACCOUNT = "kyverno-background-controller"
NAME = "write-kyverno-generated-externalsecrets"
RULES = [
    rule(["external-secrets.io"], ["externalsecrets", "secretstores"], WRITE),
    rule([""], ["secrets"], READ),
]
NOTES = (
    "Grants Kyverno's background controller the permissions to generate "
    "externalsecrets.external-secrets.io and secretstores.external-secrets.io resources "
    "from the Secrets which trigger them. It is bound to that controller in each "
    "organization namespace."
)
TRIGGERS_NAME = "list-kyverno-generating-policy-triggers"
TRIGGERS_RULES = [rule([""], ["secrets"], ["list"])]


def kyverno_objects(orgs: list[str]) -> list[dict]:
    """The ClusterRole, and its RoleBinding to the background controller in each of `orgs`, and
    the list of Secrets across the cluster."""
    subject = {
        "kind": "ServiceAccount",
        "name": SERVICE_ACCOUNT,
        "namespace": NAMESPACE,
    }
    ref = role_ref("ClusterRole", NAME)
    return (
        [cluster_role(NAME, RULES, NOTES)]
        + [role_binding(NAME, ns, ref, [subject]) for ns in orgs]
        + [
            cluster_role(TRIGGERS_NAME, TRIGGERS_RULES),
            cluster_role_binding(TRIGGERS_NAME, TRIGGERS_NAME, [subject]),
        ]
    )
