"""External Secrets Operator in the test cluster, with a stand-in for the customer's store.

ESO runs on every Giant Swarm management cluster, and the customer creates a
`ClusterSecretStore` that reads their secret manager. The test installs ESO and creates
the store of docs/appendices.md, "Secret store for testing", whose fake provider keeps
the values in the store itself. The examples' `ExternalSecret`s read it.
"""

import time
from collections.abc import Iterator

import pykube
import pytest
from conftest import HELM_URL, apply, run_tool
from eso_kinds import ClusterSecretStoreCR
from fake_store import FAKE_STORE_DATA
from pytest_helm_charts.clusters import Cluster
from workload_cluster_secrets import COMMON, controller_egress

ESO_RELEASE_NAME = "external-secrets"
ESO_NAMESPACE = "external-secrets"
# the External Secrets Operator Giant Swarm ships, from giantswarm/external-secrets
ESO_CHART = "oci://gsoci.azurecr.io/charts/giantswarm/external-secrets"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/external-secrets
ESO_CHART_VERSION = "2.14.0"
ESO_READY_TIMEOUT_SEC = 300
# the webhook that validates the store can refuse it for a moment after the install, until
#  ESO's cert controller has given it its certificate
STORE_CREATE_TIMEOUT_SEC = 120

SECRET_STORE = {
    "apiVersion": "external-secrets.io/v1",
    "kind": "ClusterSecretStore",
    "metadata": {"name": "gitops-test"},
    "spec": {
        "provider": {
            "fake": {
                "data": [
                    *FAKE_STORE_DATA,
                    {"key": "workload-clusters-common-token", "value": COMMON.value},
                ]
            }
        }
    },
}


class StoreTimeoutError(TimeoutError):
    """ESO's webhook kept refusing the store."""

    def __init__(self, name: str, timeout_sec: int) -> None:
        super().__init__(
            f"ClusterSecretStore '{name}' wasn't created in {timeout_sec} s."
        )


def create_store(api: pykube.HTTPClient, timeout_sec: int) -> ClusterSecretStoreCR:
    """Create the store, retrying while ESO's webhook refuses it."""
    store = ClusterSecretStoreCR(api, SECRET_STORE)
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            apply(store)
        except pykube.http.HTTPError as e:
            if time.monotonic() >= deadline:
                raise StoreTimeoutError(store.name, timeout_sec) from e
        else:
            return store
        time.sleep(2)


def helm(kube_config: str, *args: str) -> None:
    run_tool("helm", HELM_URL, *args, "--kubeconfig", kube_config)


@pytest.fixture(scope="module")
def external_secrets(kube_cluster: Cluster, kube_config: str) -> Iterator[None]:
    """Install ESO and create the fake store; remove both again in the end."""
    helm(
        kube_config,
        "upgrade",
        "--install",
        ESO_RELEASE_NAME,
        ESO_CHART,
        "--version",
        ESO_CHART_VERSION,
        "--namespace",
        ESO_NAMESPACE,
        "--create-namespace",
        # As Giant Swarm's management-cluster-bases sets it, so Kyverno admits the PolicyException.
        "--set",
        "giantswarm.policyExceptionNamespace=giantswarm",
        # The chart's 100m CPU per pod is sized for a management cluster; on the one kind node
        # it leaves the workload cluster's pods Pending with "Insufficient cpu".
        "--set",
        "giantswarm.resources.externalSecrets.requests.cpu=10m",
        "--set",
        "giantswarm.resources.certController.requests.cpu=10m",
        "--set",
        "giantswarm.resources.webhook.requests.cpu=10m",
        "--wait",
        "--timeout",
        f"{ESO_READY_TIMEOUT_SEC}s",
    )
    try:
        with controller_egress(
            kube_cluster.kube_client, ESO_NAMESPACE, ESO_RELEASE_NAME
        ):
            store = create_store(kube_cluster.kube_client, STORE_CREATE_TIMEOUT_SEC)
            yield
            store.delete()
    finally:
        helm(
            kube_config,
            "uninstall",
            ESO_RELEASE_NAME,
            "--ignore-not-found",
            "--namespace",
            ESO_NAMESPACE,
            "--wait",
        )
