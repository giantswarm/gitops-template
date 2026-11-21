"""Reads a Secret from the test's vCluster through its generated SecretStore.

workload_cluster_secret_stores.py calls it once the store is Ready: it creates a Secret in the
vCluster and an ExternalSecret on the management cluster that reads it through the store, and
checks that the Secret the ExternalSecret writes holds the vCluster's value.
"""

import base64

import pykube
from conftest import WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE as NAMESPACE
from eso_kinds import ExternalSecretCR
from eso_ready import wait_ready

# the namespace the generated store reads in the workload cluster
REMOTE_NAMESPACE = "default"
# the Secret the check reads from the vCluster through the store
REMOTE_NAME = "eso-cluster-auth-test"
REMOTE_VALUE = "read-from-the-workload-cluster"
# ESO retries an ExternalSecret whose store isn't ready yet
SYNC_TIMEOUT_SEC = 180


def synced_value_problems(secret: dict | None) -> list[str]:
    """Why the Secret the ExternalSecret wrote doesn't hold REMOTE_VALUE, if it doesn't."""
    if secret is None:
        return [f"Secret '{NAMESPACE}/{REMOTE_NAME}' doesn't exist"]
    value = (secret.get("data") or {}).get("value", "")
    if base64.b64decode(value).decode() != REMOTE_VALUE:
        return [
            f"Secret '{NAMESPACE}/{REMOTE_NAME}' doesn't hold the workload cluster's value"
        ]
    return []


def synced_secret(api: pykube.HTTPClient) -> dict | None:
    secret = (
        pykube.Secret.objects(api)
        .filter(namespace=NAMESPACE)
        .get_or_none(name=REMOTE_NAME)
    )
    return secret.obj if secret else None


def read_through_store(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient, store: str
) -> None:
    """Create REMOTE_NAME in the vCluster and wait for an ExternalSecret to read its value."""
    remote = pykube.Secret(
        workload_cluster,
        {
            "metadata": {"name": REMOTE_NAME, "namespace": REMOTE_NAMESPACE},
            "stringData": {"value": REMOTE_VALUE},
        },
    )
    external_secret = ExternalSecretCR(
        api,
        {
            "apiVersion": ExternalSecretCR.version,
            "kind": ExternalSecretCR.kind,
            "metadata": {"name": REMOTE_NAME, "namespace": NAMESPACE},
            "spec": {
                "secretStoreRef": {"kind": "SecretStore", "name": store},
                "target": {"name": REMOTE_NAME},
                "data": [
                    {
                        "secretKey": "value",
                        "remoteRef": {"key": REMOTE_NAME, "property": "value"},
                    }
                ],
            },
        },
    )
    try:
        remote.create()
        external_secret.create()
        wait_ready(
            api,
            ExternalSecretCR,
            NAMESPACE,
            REMOTE_NAME,
            "the workload cluster's Secret wasn't read through its store",
            SYNC_TIMEOUT_SEC,
            lambda: synced_value_problems(synced_secret(api)),
        )
    finally:
        for obj in (external_secret, remote):
            if obj.exists():
                obj.delete()
