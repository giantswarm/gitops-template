"""What ESO in the test cluster needs to push Secrets into the workload cluster, as
apps/workload-cluster-secrets does, and the check of the generated password it pushes.

ESO reaches the workload cluster, the test's vCluster, by the name of its Service. Giant
Swarm's ESO chart has a NetworkPolicy that selects every pod of the release and lets it reach
only ports 443 and 6443 in the private ranges 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 and
100.64.0.0/10, with no DNS. On a management cluster its CiliumNetworkPolicy also lets it reach
the cluster and the world; the kind cluster has no Cilium, so the test adds a NetworkPolicy
that does the same. Keep it, or one like it, as long as the chart's NetworkPolicy is there:
without it, ESO can't push into the vCluster.
"""

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from typing import NamedTuple

import pykube
from conftest import apply
from flux_reconcile import wait_until
from pykube.objects import NamespacedAPIObject

WORKLOAD_CLUSTER_NAMESPACE = "default"
# ESO pushes the Secrets once the cluster's apps Kustomization has applied the PushSecrets
PUSH_TIMEOUT_SEC = 300


class PushedSecret(NamedTuple):
    """A Secret a PushSecret writes into the workload cluster, the key it writes, and the value
    it must have; with no value, any one but an empty one will do."""

    name: str
    key: str
    value: str = ""


# common-secret.yaml pushes the value the store of external_secrets.py keeps
COMMON = PushedSecret("common-secret", "token", "common-token-from-secret-manager")
# generated-password.yaml pushes a password the generator makes anew each run
GENERATED = PushedSecret("generated-password", "password")


class NetworkPolicy(NamespacedAPIObject):
    version = "networking.k8s.io/v1"
    endpoint = "networkpolicies"
    kind = "NetworkPolicy"


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


@contextmanager
def controller_egress(
    api: pykube.HTTPClient, namespace: str, release: str
) -> Iterator[None]:
    """Let the ESO pods of `release` reach anything while the block runs, and remove the
    NetworkPolicy again afterwards, however the block ends."""
    policy = apply(controller_egress_policy(api, namespace, release))
    try:
        yield
    finally:
        policy.delete()


def pushed_problems(pushed: PushedSecret, secret: dict | None) -> list[str]:
    """Why `secret`, as the workload cluster has it, isn't what `pushed` says, if it isn't."""
    name = f"{WORKLOAD_CLUSTER_NAMESPACE}/{pushed.name}"
    if secret is None:
        return [f"Secret '{name}' isn't in the workload cluster"]
    encoded = (secret.get("data") or {}).get(pushed.key)
    if not encoded:
        return [f"Secret '{name}' has no '{pushed.key}'"]
    if pushed.value and base64.b64decode(encoded).decode() != pushed.value:
        return [f"Secret '{name}' has another '{pushed.key}' than the store's"]
    return []


def check_secrets_pushed(workload_cluster: pykube.HTTPClient) -> None:
    """Wait for the Secrets of apps/workload-cluster-secrets to reach the workload cluster."""

    def problems() -> list[str]:
        found = pykube.Secret.objects(workload_cluster).filter(
            namespace=WORKLOAD_CLUSTER_NAMESPACE
        )
        return [
            problem
            for pushed in (COMMON, GENERATED)
            for problem in pushed_problems(
                pushed, getattr(found.get_or_none(name=pushed.name), "obj", None)
            )
        ]

    wait_until(problems, PUSH_TIMEOUT_SEC, "the Secrets weren't pushed")
