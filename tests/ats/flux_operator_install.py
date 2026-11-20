"""Flux Operator in the test cluster, as on a Giant Swarm management cluster.

The ResourceSet examples are Flux Operator objects, so Flux Operator has to run before Flux
applies the repository: test_flux_objects.py requests the `flux_operator` fixture before
`gitops_deployment`. The chart is the one Giant Swarm ships, from flux-operator-app, at the
version management-cluster-bases deploys, in the namespace it deploys it to.
"""

from pathlib import Path

import pytest
from conftest import HELM_URL, run_tool

FLUX_OPERATOR_CHART = "oci://gsoci.azurecr.io/charts/giantswarm/flux-operator"
# renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/flux-operator
FLUX_OPERATOR_CHART_VERSION = "0.9.0"
FLUX_OPERATOR_NAMESPACE = "flux-giantswarm"
FLUX_OPERATOR_READY_TIMEOUT_SEC = 300
# installs the CRDs and turns off what needs CRDs the kind cluster doesn't have; the file says
#  which
FLUX_OPERATOR_VALUES_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "flux-operator-values.yaml"
)


@pytest.fixture(scope="module")
def flux_operator(kube_config: str) -> None:
    """Install Flux Operator and wait for it.

    It isn't uninstalled: the test cluster goes away with it.
    """
    run_tool(
        "helm",
        HELM_URL,
        "upgrade",
        "--install",
        "flux-operator",
        FLUX_OPERATOR_CHART,
        "--version",
        FLUX_OPERATOR_CHART_VERSION,
        "--namespace",
        FLUX_OPERATOR_NAMESPACE,
        "--create-namespace",
        "--values",
        str(FLUX_OPERATOR_VALUES_FILE),
        "--wait",
        "--timeout",
        f"{FLUX_OPERATOR_READY_TIMEOUT_SEC}s",
        "--kubeconfig",
        kube_config,
    )
