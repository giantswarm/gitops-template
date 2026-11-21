"""External Secrets Operator in the test cluster, with a stand-in for the customer's store.

ESO runs on every Giant Swarm management cluster, and the customer creates a `SecretStore`
that reads their secret manager in each namespace that reads secrets, `default` and their
`org-*` namespace: they can't create a `ClusterSecretStore`. The test installs ESO and creates
the stores of docs/how-to/external-secrets.md, "A secret store for testing", whose fake
provider keeps the values in the store itself. The examples' `ExternalSecret`s read them. The fixture creates the
store in `default` before Flux applies the repository; organization_operator calls
`organization_store` once it has created the organisation's namespace.
"""

import time
from collections.abc import Iterator

import pykube
import pytest
from conftest import HELM_URL, apply, run_tool
from eso_kinds import SecretStoreCR
from fake_store import DEFAULT_STORE_NAMESPACE, secret_stores
from pytest_helm_charts.clusters import Cluster
from workload_cluster_secrets import controller_egress

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


class StoreTimeoutError(TimeoutError):
    """ESO's webhook kept refusing the store."""

    def __init__(self, name: str, timeout_sec: int) -> None:
        super().__init__(f"SecretStore '{name}' wasn't created in {timeout_sec} s.")


class MissingNamespaceError(Exception):
    """The namespace of a store doesn't exist, so no retry can create the store."""

    def __init__(self, namespace: str) -> None:
        super().__init__(
            f"Namespace '{namespace}' doesn't exist, so its SecretStore can't be created."
        )


def namespace_exists(api: pykube.HTTPClient, name: str) -> bool:
    return pykube.Namespace.objects(api).get_or_none(name=name) is not None


def create_store(
    api: pykube.HTTPClient, manifest: dict, timeout_sec: int
) -> SecretStoreCR:
    """Create the store, retrying while ESO's webhook refuses it. Fail at once when its
    namespace doesn't exist."""
    store = SecretStoreCR(api, manifest)
    if not namespace_exists(api, store.namespace):
        raise MissingNamespaceError(store.namespace)
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            apply(store)
        except pykube.http.HTTPError as e:
            if time.monotonic() >= deadline:
                raise StoreTimeoutError(
                    f"{store.namespace}/{store.name}", timeout_sec
                ) from e
        else:
            return store
        time.sleep(2)


def organization_store(api: pykube.HTTPClient, namespace: str) -> list[SecretStoreCR]:
    """Create the test's store in the organisation's `namespace`, as the customer does."""
    return [
        create_store(api, s, STORE_CREATE_TIMEOUT_SEC)
        for s in secret_stores([namespace])
    ]


def helm(kube_config: str, *args: str) -> None:
    run_tool("helm", HELM_URL, *args, "--kubeconfig", kube_config)


@pytest.fixture(scope="module")
def external_secrets(
    kube_cluster: Cluster, kube_config: str, init_namespaces: object
) -> Iterator[None]:
    """Install ESO and create the fake store in `default`; remove them again in the end."""
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
            stores = [
                create_store(kube_cluster.kube_client, s, STORE_CREATE_TIMEOUT_SEC)
                for s in secret_stores([DEFAULT_STORE_NAMESPACE])
            ]
            yield
            for store in stores:
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
