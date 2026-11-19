"""The External Secrets Operator kinds of apps/workload-cluster-secrets, which pushes Secrets into
the workload cluster, and what ESO in the test cluster needs to reach that cluster.

ESO reaches the workload cluster, the test's vCluster, by the name of its Service. The
NetworkPolicy of Giant Swarm's ESO chart lets the controller reach API servers on ports 443 and
6443 only, with no DNS. On a management cluster its CiliumNetworkPolicy also lets it reach the
cluster and the world; the kind cluster has no Cilium, so the test adds a NetworkPolicy that does
the same.
"""

import pykube
from pykube.objects import NamespacedAPIObject


class SecretStoreCR(NamespacedAPIObject):
    version = "external-secrets.io/v1"
    endpoint = "secretstores"
    kind = "SecretStore"


class PushSecretCR(NamespacedAPIObject):
    version = "external-secrets.io/v1alpha1"
    endpoint = "pushsecrets"
    kind = "PushSecret"


class PasswordCR(NamespacedAPIObject):
    version = "generators.external-secrets.io/v1alpha1"
    endpoint = "passwords"
    kind = "Password"


class NetworkPolicy(NamespacedAPIObject):
    version = "networking.k8s.io/v1"
    endpoint = "networkpolicies"
    kind = "NetworkPolicy"


# the kinds apps/workload-cluster-secrets applies, besides ExternalSecret
WORKLOAD_CLUSTER_SECRETS_KINDS: dict[str, type[NamespacedAPIObject]] = {
    "SecretStore": SecretStoreCR,
    "PushSecret": PushSecretCR,
    "Password": PasswordCR,
}


def controller_egress_policy(
    api: pykube.HTTPClient, namespace: str, release: str
) -> NetworkPolicy:
    """A NetworkPolicy that lets the ESO pods of `release` reach anything, as the chart's
    CiliumNetworkPolicy does on a management cluster."""
    return NetworkPolicy(
        api,
        {
            "apiVersion": NetworkPolicy.version,
            "kind": NetworkPolicy.kind,
            "metadata": {"name": f"{release}-egress-test", "namespace": namespace},
            "spec": {
                "podSelector": {"matchLabels": {"app.kubernetes.io/instance": release}},
                "egress": [{}],
                "policyTypes": ["Egress"],
            },
        },
    )
