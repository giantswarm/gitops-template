"""Checks the PushSecret example that pushes a Secret through the generated SecretStore.

The out-of-band-no-flux cluster's apps push a password, made by ESO's Password generator, into
the workload cluster through `<cluster>-eso-cluster-store`, which the Kyverno policy
`generate-eso-cluster-auth-from-kubeconfig` generates. The test's vCluster stands in for the
cluster. workload_cluster_secret_stores.py calls the check once the store is Ready: it waits
for the PushSecret to get Ready and for the Secret it writes to hold the password.
"""

import base64

import pykube
from conftest import WORKLOAD_CLUSTER_VCLUSTER_NAME as CLUSTER
from eso_kinds import PushSecretCR
from eso_ready import wait_ready
from workload_cluster_secret_read import NAMESPACE, REMOTE_NAMESPACE

# the PushSecret of apps/pushed-password and what it writes in the workload cluster
PUSH_SECRET = f"{CLUSTER}-pushed-password"
PUSHED_NAME = "pushed-password"
PUSHED_KEY = "password"
# the Password generator's `length`: a password of another length wasn't the generator's
PASSWORD_LENGTH = 32
# ESO retries a PushSecret whose store doesn't exist yet
PUSH_TIMEOUT_SEC = 300


def pushed_secret_problems(secret: dict | None) -> list[str]:
    """Why the Secret in the workload cluster doesn't hold a password of the generator's
    length, if it doesn't."""
    name = f"{REMOTE_NAMESPACE}/{PUSHED_NAME}"
    if secret is None:
        return [f"Secret '{name}' isn't in the workload cluster"]
    encoded = (secret.get("data") or {}).get(PUSHED_KEY)
    if not encoded:
        return [f"Secret '{name}' has no '{PUSHED_KEY}'"]
    length = len(base64.b64decode(encoded).decode())
    if length != PASSWORD_LENGTH:
        return [
            f"Secret '{name}' has a '{PUSHED_KEY}' of {length} characters,"
            f" not {PASSWORD_LENGTH}"
        ]
    return []


def pushed_secret(workload_cluster: pykube.HTTPClient) -> dict | None:
    secret = (
        pykube.Secret.objects(workload_cluster)
        .filter(namespace=REMOTE_NAMESPACE)
        .get_or_none(name=PUSHED_NAME)
    )
    return secret.obj if secret else None


def check_secret_pushed(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """Wait for the PushSecret to get Ready and its Secret to reach the workload cluster."""
    wait_ready(
        api,
        PushSecretCR,
        NAMESPACE,
        PUSH_SECRET,
        "the password wasn't pushed through the workload cluster's store",
        PUSH_TIMEOUT_SEC,
        lambda: pushed_secret_problems(pushed_secret(workload_cluster)),
    )
