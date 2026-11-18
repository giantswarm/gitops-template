"""Kyverno in the test cluster, as on a Giant Swarm management cluster.

The shared-objects example is a Kyverno ClusterPolicy, so Kyverno has to run before Flux applies
the repository: test_flux_objects.py requests the `kyverno` fixture before any other.
"""

import pytest
from conftest import HELM_URL, run_tool

KYVERNO_CHART_REPO = "https://kyverno.github.io/kyverno/"
# The chart kyverno-app 0.26.1 ships to the management clusters: Kyverno v1.19.2.
# renovate: datasource=helm depName=kyverno registryUrl=https://kyverno.github.io/kyverno/
KYVERNO_CHART_VERSION = "3.9.2"
KYVERNO_NAMESPACE = "kyverno"
KYVERNO_READY_TIMEOUT_SEC = 300


@pytest.fixture(scope="module")
def kyverno(kube_config: str) -> None:
    """Install Kyverno's admission and background controllers, which generate rules need.

    It isn't uninstalled: the test cluster goes away with it.
    """
    run_tool(
        "helm",
        HELM_URL,
        "upgrade",
        "--install",
        "kyverno",
        "kyverno",
        "--repo",
        KYVERNO_CHART_REPO,
        "--version",
        KYVERNO_CHART_VERSION,
        "--namespace",
        KYVERNO_NAMESPACE,
        "--create-namespace",
        # the example needs neither
        "--set",
        "cleanupController.enabled=false",
        "--set",
        "reportsController.enabled=false",
        "--wait",
        "--timeout",
        f"{KYVERNO_READY_TIMEOUT_SEC}s",
        "--kubeconfig",
        kube_config,
    )
