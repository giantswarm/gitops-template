"""The rights rbac-operator gives Kyverno's background controller in every organisation
namespace of a Giant Swarm management cluster, so that a Kyverno policy there can generate
ExternalSecrets and SecretStores from the Secrets that trigger it, such as the example in
organizations/ORG_NAME/namespace/workload-cluster-secret-stores.

Copied from giantswarm/rbac-operator at 80aed29e11e49eac3a7f77b601c6df124e66cfe4 (SOURCE), not
released yet: service/controller/defaultnamespace/resource/clusterroles/create.go
createWriteKyvernoGeneratedExternalSecretsClusterRole (the ClusterRole),
service/controller/rbac/resource/automation/create.go EnsureCreated (the RoleBinding in each
organisation namespace) and pkg/key/key.go (the names). automation_bindings plans them with the
`automation` ServiceAccounts' objects.
"""

from automation_roles import READ, WRITE, rule
from rbac_manifests import cluster_role, role_binding, role_ref

SOURCE = "giantswarm/rbac-operator@80aed29e11e49eac3a7f77b601c6df124e66cfe4"
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


def kyverno_objects(orgs: list[str]) -> list[dict]:
    """The ClusterRole, and its RoleBinding to the background controller in each of `orgs`."""
    subject = {
        "kind": "ServiceAccount",
        "name": SERVICE_ACCOUNT,
        "namespace": NAMESPACE,
    }
    ref = role_ref("ClusterRole", NAME)
    return [cluster_role(NAME, RULES, NOTES)] + [
        role_binding(NAME, ns, ref, [subject]) for ns in orgs
    ]
