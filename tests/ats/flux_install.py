"""Flux in the test cluster, from the flux-app chart a Giant Swarm management cluster runs.

The chart is the one Giant Swarm ships, at the version `GITOPS_FLUX_APP_VERSION` names. helm
installs it as the release `flux-app` in the namespace where the test creates its Flux objects.
"""

import logging
from pathlib import Path

import pytest
from conftest import FLUX_NAMESPACE_NAME, HELM_URL, GitOpsTestConfig, run_tool

FLUX_APP_CHART = "oci://gsoci.azurecr.io/charts/giantswarm/flux-app"
FLUX_APP_READY_TIMEOUT_SEC = 300
# turns off what needs CRDs the kind cluster doesn't have; the file says which
FLUX_APP_VALUES_FILE = (
    Path(__file__).resolve().parent / "fixtures" / "flux-app-values.yaml"
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def flux_app_deployment(kube_config: str, gitops_test_config: GitOpsTestConfig) -> None:
    """Install flux-app and wait for it.

    It isn't uninstalled: the test cluster goes away with it.
    """
    version = gitops_test_config.flux_app_version
    logger.debug(f"Installing 'flux-app' in version '{version}'.")
    run_tool(
        "helm",
        HELM_URL,
        "upgrade",
        "--install",
        "flux-app",
        FLUX_APP_CHART,
        "--version",
        version,
        "--namespace",
        FLUX_NAMESPACE_NAME,
        "--values",
        str(FLUX_APP_VALUES_FILE),
        "--wait",
        "--timeout",
        f"{FLUX_APP_READY_TIMEOUT_SEC}s",
        "--kubeconfig",
        kube_config,
    )
