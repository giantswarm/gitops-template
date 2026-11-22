"""Checks the example that pushes a cluster's kubeconfig to another cluster.

The out-of-band-no-flux cluster's apps push its kubeconfig Secret, as Cluster API writes it,
into the cluster `tools-cluster`, through `tools-cluster-eso-cluster-store`, which the Kyverno
policy in the organisation's multicluster/secret-stores generates from that cluster's own
kubeconfig Secret. The test has no tools cluster: organization_operator writes a kubeconfig
Secret for it with the vCluster's kubeconfig, so the vCluster stands in for it as well.
workload_cluster_secret_stores.py calls the check once the stores are Ready: it waits for the
PushSecret to get Ready and for the Secret it writes to hold the kubeconfig.
"""

import pykube
import yaml
from conftest import WORKLOAD_CLUSTER_KUBECONFIG_NAME
from conftest import WORKLOAD_CLUSTER_VCLUSTER_NAME as CLUSTER
from eso_kinds import PushSecretCR
from eso_ready import wait_ready
from workload_cluster_secret_read import NAMESPACE, REMOTE_NAMESPACE

# the cluster apps/pushed-kubeconfig pushes to
TOOLS_CLUSTER = "tools-cluster"
CLUSTER_NAME_LABEL = "cluster.x-k8s.io/cluster-name"
# the PushSecret of apps/pushed-kubeconfig, and what it writes in the tools cluster: the
#  kubeconfig Secret under its own name and key
PUSH_SECRET = f"{CLUSTER}-pushed-kubeconfig"
PUSHED_NAME = WORKLOAD_CLUSTER_KUBECONFIG_NAME
PUSHED_KEY = "value"
# ESO retries a PushSecret whose store doesn't exist yet
PUSH_TIMEOUT_SEC = 300


def cluster_kubeconfig_secret(cluster: str, namespace: str, kubeconfig: dict) -> dict:
    """The kubeconfig Secret of `cluster` in `namespace`, labelled and typed as Cluster API
    writes it, which the Kyverno policy `generate-eso-cluster-auth-from-kubeconfig` matches.
    """
    return {
        "metadata": {
            "name": f"{cluster}-kubeconfig",
            "namespace": namespace,
            "labels": {CLUSTER_NAME_LABEL: cluster},
        },
        "type": "cluster.x-k8s.io/secret",
        "stringData": {"value": yaml.safe_dump(kubeconfig)},
    }


def pushed_kubeconfig_problems(pushed: dict | None, source: dict | None) -> list[str]:
    """Why the Secret in the tools cluster doesn't hold the kubeconfig of the Secret `source`
    on the management cluster, if it doesn't."""
    if source is None:
        return [
            f"the kubeconfig Secret '{PUSHED_NAME}' isn't on the management cluster"
        ]
    name = f"{REMOTE_NAMESPACE}/{PUSHED_NAME}"
    if pushed is None:
        return [f"Secret '{name}' isn't in the tools cluster"]
    value = (pushed.get("data") or {}).get(PUSHED_KEY)
    if value != (source.get("data") or {}).get(PUSHED_KEY):
        return [
            f"Secret '{name}' in the tools cluster doesn't hold the kubeconfig of the "
            "cluster it was pushed from"
        ]
    return []


def secret(api: pykube.HTTPClient, namespace: str, name: str) -> dict | None:
    found = (
        pykube.Secret.objects(api).filter(namespace=namespace).get_or_none(name=name)
    )
    return found.obj if found else None


def check_kubeconfig_pushed(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """Wait for the PushSecret to get Ready and the kubeconfig to reach the tools cluster."""
    wait_ready(
        api,
        PushSecretCR,
        NAMESPACE,
        PUSH_SECRET,
        "the kubeconfig wasn't pushed through the tools cluster's store",
        PUSH_TIMEOUT_SEC,
        lambda: pushed_kubeconfig_problems(
            secret(workload_cluster, REMOTE_NAMESPACE, PUSHED_NAME),
            secret(api, NAMESPACE, PUSHED_NAME),
        ),
    )
