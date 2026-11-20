"""Checks of the kubeconfig Secret the test writes for a new cluster and of how the credentials
the policy writes are judged; they need no cluster."""

from workload_cluster_secret_read import NAMESPACE
from workload_cluster_secret_stores import (
    AUTH_KEYS,
    auth_secret_problems,
    new_cluster_kubeconfig,
)

KUBECONFIG = {
    "metadata": {
        "name": "out-of-band-no-flux-kubeconfig",
        "namespace": NAMESPACE,
        "labels": {"cluster.x-k8s.io/cluster-name": "out-of-band-no-flux"},
        "resourceVersion": "1",
        "uid": "x",
    },
    "type": "cluster.x-k8s.io/secret",
    "data": {"value": "a3ViZWNvbmZpZw=="},
}


def test_new_cluster_kubeconfig_is_written_as_cluster_api_writes_it() -> None:
    assert new_cluster_kubeconfig(KUBECONFIG, "new-cluster") == {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "new-cluster-kubeconfig",
            "namespace": NAMESPACE,
            "labels": {"cluster.x-k8s.io/cluster-name": "new-cluster"},
        },
        "type": "cluster.x-k8s.io/secret",
        "data": {"value": "a3ViZWNvbmZpZw=="},
    }


def test_auth_secret_problems_none_with_every_key() -> None:
    secret = {"data": {k: "eA==" for k in AUTH_KEYS}}
    assert auth_secret_problems(secret, "c-eso-cluster-auth") == []


def test_auth_secret_problems_missing_keys() -> None:
    secret = {"data": {"tls.crt": "eA==", "server": ""}}
    assert auth_secret_problems(secret, "c-eso-cluster-auth") == [
        f"Secret '{NAMESPACE}/c-eso-cluster-auth' lacks ['ca.crt', 'server', 'tls.key']"
    ]


def test_auth_secret_problems_missing() -> None:
    assert auth_secret_problems(None, "c-eso-cluster-auth") == [
        f"Secret '{NAMESPACE}/c-eso-cluster-auth' doesn't exist"
    ]
