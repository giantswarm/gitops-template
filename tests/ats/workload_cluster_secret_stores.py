"""The Kyverno `Policy` `generate-eso-cluster-auth-from-kubeconfig` in the organisation's
namespace gives every workload cluster a SecretStore.

From the cluster's kubeconfig Secret the policy generates an ExternalSecret that writes the
cluster's credentials into `<cluster>-eso-cluster-auth`, through the organisation's SecretStore
`default`, and from that Secret the SecretStore `<cluster>-eso-cluster-store` that reaches the
cluster. The test's vCluster and its kubeconfig Secret stand in for a workload cluster that
exists before the policy. The check waits for the chain, reads a Secret from the vCluster
through the store, and checks the example's PushSecret wrote its Secret into the vCluster
through it. It then writes a kubeconfig Secret for a new cluster, as Cluster API does, and
waits for the policy to react to it. test_flux_objects.py runs it once the Kustomizations are
ready.
"""

import pykube
import pytest
from conftest import WORKLOAD_CLUSTER_KUBECONFIG_NAME
from conftest import WORKLOAD_CLUSTER_VCLUSTER_NAME as CLUSTER
from eso_kinds import ExternalSecretCR, SecretStoreCR
from eso_ready import wait_ready
from workload_cluster_secret_push import check_secret_pushed
from workload_cluster_secret_read import NAMESPACE, read_through_store

# the store, in organizations/ORG_NAME/namespace/workload-cluster-secret-stores, that reads the
# organisation namespace's own Secrets
ORGANIZATION_STORE = "default"
AUTH_KEYS = {"tls.crt", "tls.key", "ca.crt", "server"}
# the cluster whose kubeconfig Secret the test writes once the policy is in place; it reaches
# the vCluster too
NEW_CLUSTER = "new-cluster"
CLUSTER_NAME_LABEL = "cluster.x-k8s.io/cluster-name"
# Kyverno generates within seconds; ESO retries a store or ExternalSecret that isn't ready yet
SYNC_TIMEOUT_SEC = 180


def auth_secret_problems(secret: dict | None, name: str) -> list[str]:
    """Why the Secret `name` doesn't hold a cluster's credentials, if it doesn't."""
    if secret is None:
        return [f"Secret '{NAMESPACE}/{name}' doesn't exist"]
    missing = AUTH_KEYS - {k for k, v in (secret.get("data") or {}).items() if v}
    return [f"Secret '{NAMESPACE}/{name}' lacks {sorted(missing)}"] if missing else []


def new_cluster_kubeconfig(source: dict, cluster: str) -> dict:
    """A kubeconfig Secret for `cluster`, labelled and typed as Cluster API writes it, with the
    kubeconfig of the Secret `source`."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": f"{cluster}-kubeconfig",
            "namespace": source["metadata"]["namespace"],
            "labels": {CLUSTER_NAME_LABEL: cluster},
        },
        "type": source["type"],
        "data": {"value": source["data"]["value"]},
    }


def secret(api: pykube.HTTPClient, name: str) -> dict | None:
    found = (
        pykube.Secret.objects(api).filter(namespace=NAMESPACE).get_or_none(name=name)
    )
    return found.obj if found else None


def wait_cluster_store(api: pykube.HTTPClient, cluster: str, when: str) -> None:
    """Wait for what the policy generates for `cluster`: the ExternalSecret that writes its
    credentials, and the SecretStore that reaches it."""
    auth = f"{cluster}-eso-cluster-auth"
    wait_ready(
        api,
        ExternalSecretCR,
        NAMESPACE,
        auth,
        f"the credentials of {when} weren't written from its kubeconfig",
        SYNC_TIMEOUT_SEC,
        lambda: auth_secret_problems(secret(api, auth), auth),
    )
    wait_ready(
        api,
        SecretStoreCR,
        NAMESPACE,
        f"{cluster}-eso-cluster-store",
        f"the SecretStore of {when} didn't get Ready",
        SYNC_TIMEOUT_SEC,
    )


def check_new_cluster(api: pykube.HTTPClient) -> None:
    """Write a kubeconfig Secret for NEW_CLUSTER and wait for the policy to react to it."""
    source = secret(api, WORKLOAD_CLUSTER_KUBECONFIG_NAME)
    if source is None:
        pytest.fail(f"Secret '{NAMESPACE}/{WORKLOAD_CLUSTER_KUBECONFIG_NAME}' is gone")
        return
    kubeconfig = pykube.Secret(api, new_cluster_kubeconfig(source, NEW_CLUSTER))
    try:
        kubeconfig.create()
        wait_cluster_store(api, NEW_CLUSTER, "a new cluster")
    finally:
        if kubeconfig.exists():
            kubeconfig.delete()


def check_workload_cluster_secret_store(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """Wait for the policy's chain for the vCluster, read a Secret through its store, check
    the example's PushSecret wrote one through it, then check the policy reacts to a new
    cluster."""
    wait_ready(
        api,
        SecretStoreCR,
        NAMESPACE,
        ORGANIZATION_STORE,
        "the organisation's SecretStore didn't get Ready",
        SYNC_TIMEOUT_SEC,
    )
    wait_cluster_store(api, CLUSTER, "the existing cluster")
    read_through_store(api, workload_cluster, f"{CLUSTER}-eso-cluster-store")
    check_secret_pushed(api, workload_cluster)
    check_new_cluster(api)
