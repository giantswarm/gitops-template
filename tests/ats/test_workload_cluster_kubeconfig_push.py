"""Checks of the stand-in kubeconfig Secret of the cluster that receives a pushed kubeconfig, and
of how the kubeconfig it receives is judged; they need no cluster."""

import base64

from workload_cluster_kubeconfig_push import (
    PUSHED_KEY,
    PUSHED_NAME,
    TOOLS_CLUSTER,
    cluster_kubeconfig_secret,
    pushed_kubeconfig_problems,
)
from workload_cluster_secret_read import REMOTE_NAMESPACE

KUBECONFIG = {"apiVersion": "v1", "kind": "Config", "clusters": []}
SOURCE = {"data": {PUSHED_KEY: base64.b64encode(b"kubeconfig").decode()}}


def test_cluster_kubeconfig_secret_is_written_as_cluster_api_writes_it() -> None:
    assert cluster_kubeconfig_secret(TOOLS_CLUSTER, "org-a", KUBECONFIG) == {
        "metadata": {
            "name": f"{TOOLS_CLUSTER}-kubeconfig",
            "namespace": "org-a",
            "labels": {"cluster.x-k8s.io/cluster-name": TOOLS_CLUSTER},
        },
        "type": "cluster.x-k8s.io/secret",
        "stringData": {
            "value": "apiVersion: v1\nclusters: []\nkind: Config\n",
        },
    }


def test_pushed_kubeconfig_problems_none_when_it_matches_the_source() -> None:
    assert pushed_kubeconfig_problems(SOURCE, SOURCE) == []


def test_pushed_kubeconfig_problems_other_value() -> None:
    pushed = {"data": {PUSHED_KEY: base64.b64encode(b"other").decode()}}
    assert pushed_kubeconfig_problems(pushed, SOURCE) == [
        f"Secret '{REMOTE_NAMESPACE}/{PUSHED_NAME}' in the tools cluster doesn't hold the "
        "kubeconfig of the cluster it was pushed from"
    ]


def test_pushed_kubeconfig_problems_missing() -> None:
    assert pushed_kubeconfig_problems(None, SOURCE) == [
        f"Secret '{REMOTE_NAMESPACE}/{PUSHED_NAME}' isn't in the tools cluster"
    ]


def test_pushed_kubeconfig_problems_source_missing() -> None:
    assert pushed_kubeconfig_problems(SOURCE, None) == [
        f"the kubeconfig Secret '{PUSHED_NAME}' isn't on the management cluster"
    ]
