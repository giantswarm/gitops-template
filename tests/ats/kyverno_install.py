"""Kyverno in the test cluster, as on a Giant Swarm management cluster.

Kyverno runs on every Giant Swarm management cluster, and the External Secrets Operator chart
creates its PolicyExceptions only when Kyverno's CRDs are there, so Kyverno has to run before ESO
is installed: test_flux_objects.py requests the `kyverno` fixture before any other.

The charts are the ones Giant Swarm ships, from team Shield's kyverno-app and kyverno-crds, at
the versions on the management clusters. kyverno-app leaves the CRDs to kyverno-crds, so that
chart goes first. kyverno-app's pods use the `giantswarm-critical` PriorityClass and its
PolicyExceptions go in the `giantswarm` namespace, both of which every management cluster has:
the fixture installs Giant Swarm's priority-classes chart and creates the namespace first.
"""

import logging
from pathlib import Path

import pykube
import pytest
from conftest import HELM_URL, apply, run_tool
from pytest_helm_charts.clusters import Cluster

CHARTS = "oci://gsoci.azurecr.io/charts/giantswarm"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/priority-classes
PRIORITY_CLASSES_CHART_VERSION = "0.3.1"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/kyverno-crds
KYVERNO_CRDS_CHART_VERSION = "1.19.2"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/kyverno
KYVERNO_CHART_VERSION = "0.26.1"
KYVERNO_NAMESPACE = "kyverno"
# where kyverno-app puts its PolicyExceptions
GIANTSWARM_NAMESPACE = "giantswarm"
KYVERNO_READY_TIMEOUT_SEC = 300
# turns off what needs CRDs the kind cluster doesn't have; the file says which
KYVERNO_VALUES_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "kyverno-values.yaml"
)

logger = logging.getLogger(__name__)


def log_namespace_state(api: pykube.HTTPClient) -> None:
    """Log why Kyverno's pods aren't ready: their phases and waiting reasons, and the events."""
    for pod in pykube.Pod.objects(api, namespace=KYVERNO_NAMESPACE):
        status = pod.obj.get("status", {})
        waiting = [
            c["state"]["waiting"].get("reason", "")
            for c in status.get("containerStatuses", [])
            if "waiting" in c.get("state", {})
        ]
        logger.error(f"pod {pod.name}: {status.get('phase')} {waiting}")
    for event in pykube.Event.objects(api, namespace=KYVERNO_NAMESPACE):
        obj = event.obj
        logger.error(
            f"event {obj['involvedObject']['name']}: {obj.get('reason')} {obj.get('message')}"
        )


def install_chart(kube_config: str, name: str, version: str, *args: str) -> None:
    """Install Giant Swarm's chart `name` at `version` as the release `name`, and wait for it."""
    run_tool(
        "helm",
        HELM_URL,
        "upgrade",
        "--install",
        name,
        f"{CHARTS}/{name}",
        "--version",
        version,
        "--namespace",
        KYVERNO_NAMESPACE,
        "--create-namespace",
        "--wait",
        "--timeout",
        f"{KYVERNO_READY_TIMEOUT_SEC}s",
        "--kubeconfig",
        kube_config,
        *args,
    )


@pytest.fixture(scope="module")
def kyverno(kube_cluster: Cluster, kube_config: str) -> None:
    """Install the Kyverno CRDs, then Kyverno.

    It isn't uninstalled: the test cluster goes away with it.
    """
    apply(
        pykube.Namespace(
            kube_cluster.kube_client,
            {
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {"name": GIANTSWARM_NAMESPACE},
            },
        )
    )
    try:
        install_chart(kube_config, "priority-classes", PRIORITY_CLASSES_CHART_VERSION)
        install_chart(kube_config, "kyverno-crds", KYVERNO_CRDS_CHART_VERSION)
        install_chart(
            kube_config,
            "kyverno",
            KYVERNO_CHART_VERSION,
            "--values",
            str(KYVERNO_VALUES_FILE),
        )
    except Exception:
        log_namespace_state(kube_cluster.kube_client)
        raise
