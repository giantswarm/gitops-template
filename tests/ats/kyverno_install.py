"""Kyverno in the test cluster, as on a Giant Swarm management cluster.

The shared-objects example is a Kyverno ClusterPolicy, so Kyverno has to run before Flux applies
the repository: test_flux_objects.py requests the `kyverno` fixture before any other.

The charts are the ones Giant Swarm ships, from team Shield's kyverno-app and kyverno-crds, at
the versions on the management clusters. kyverno-app leaves the CRDs to kyverno-crds, so that
chart goes first.
"""

from pathlib import Path

import pytest
from conftest import HELM_URL, run_tool

CHARTS = "oci://gsoci.azurecr.io/charts/giantswarm"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/kyverno-crds
KYVERNO_CRDS_CHART_VERSION = "1.19.2"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/kyverno
KYVERNO_CHART_VERSION = "0.26.1"
KYVERNO_NAMESPACE = "kyverno"
KYVERNO_READY_TIMEOUT_SEC = 300
# turns off what needs CRDs the kind cluster doesn't have; the file says which
KYVERNO_VALUES_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "kyverno-values.yaml"
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
def kyverno(kube_config: str) -> None:
    """Install the Kyverno CRDs, then Kyverno.

    It isn't uninstalled: the test cluster goes away with it.
    """
    install_chart(kube_config, "kyverno-crds", KYVERNO_CRDS_CHART_VERSION)
    install_chart(
        kube_config,
        "kyverno",
        KYVERNO_CHART_VERSION,
        "--values",
        str(KYVERNO_VALUES_FILE),
    )
