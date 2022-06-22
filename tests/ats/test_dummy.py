import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Iterable, Any

import pytest
import requests
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.giantswarm_app_platform.app import AppFactoryFunc, ConfiguredApp
from pytest_helm_charts.k8s.deployment import wait_for_deployments_to_run

FLUX_VERSION = "0.11.0"
CLUSTER_CTL_VERSION = "1.1.4"
CLUSTER_CTL_PROVIDERS_MAP = {"aws": "v0.7.2", "azure": "v0.5.3"}

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT: int = 180
CLUSTER_CTL_URL = f"https://github.com/kubernetes-sigs/cluster-api/releases/download/v{CLUSTER_CTL_VERSION}/clusterctl-"
GS_CRDS_COMMIT_URL = "https://raw.githubusercontent.com/giantswarm/apiextensions/15836a106059cc8d201e1237adf44aec340bbab6/helm/crds-common/templates/giantswarm.yaml"

logger = logging.getLogger(__name__)


@pytest.fixture
def flux_app_deployment(kube_cluster: Cluster, app_factory: AppFactoryFunc) -> ConfiguredApp:
    flux_app = app_factory("flux-app", FLUX_VERSION, "giantswarm", "default",
                           "https://giantswarm.github.io/giantswarm-catalog/")
    wait_for_deployments_to_run(
        kube_cluster.kube_client,
        [
            "helm-controller",
            "image-automation-controller",
            "image-reflector-controller",
            "kustomize-controller",
            "notification-controller",
            "source-controller",
        ],
        FLUX_NAMESPACE_NAME,
        FLUX_DEPLOYMENTS_READY_TIMEOUT,
    )
    return flux_app


@pytest.fixture
def gs_crds(kube_cluster: Cluster) -> Iterable[Any]:
    logger.debug("Deploying Giant Swarm CRDs to the test cluster")
    yield kube_cluster.kubectl(f"create -f {GS_CRDS_COMMIT_URL}")
    logger.debug("Deleting Giant Swarm CRDs from the test cluster")
    kube_cluster.kubectl(f"delete -f {GS_CRDS_COMMIT_URL}")


@pytest.fixture
def capi_controllers() -> None:
    clusterctl_path = shutil.which("clusterctl")

    if not clusterctl_path:
        logger.debug("Cannot find existing 'clusterctl' binary, attempting to download")
        uname_info = platform.uname()
        bin_type = uname_info.system.lower()
        bin_type += "-" + "arm64" if uname_info.machine == "arm64" else "amd64"
        url = CLUSTER_CTL_URL + bin_type
        r = requests.get(url, allow_redirects=True)
        clusterctl_path = os.path.join(tempfile.gettempdir(), "clusterctl")
        open(clusterctl_path, 'wb').write(r.content)
    logger.debug(f"Using '{clusterctl_path}' to bootstrap CAPI controllers")
    infra_providers = ",".join(":".join(p) for p in CLUSTER_CTL_PROVIDERS_MAP.items())
    # FIXME: probably also needs
    # export AWS_B64ENCODED_CREDENTIALS = "${MOCK_CREDENTIALS}"
    # export AZURE_SUBSCRIPTION_ID_B64="${MOCK_CREDENTIALS}"
    # export AZURE_TENANT_ID_B64="${MOCK_CREDENTIALS}"
    # export AZURE_CLIENT_ID_B64="${MOCK_CREDENTIALS}"
    # export AZURE_CLIENT_SECRET_B64="${MOCK_CREDENTIALS}"
    # export EXP_MACHINE_POOL="true"`
    run_res = subprocess.run([clusterctl_path, "init", f"--infrastructure={infra_providers}"])
    if run_res.returncode != 0:
        logger.error(f"Error bootstrapping CAPI on test cluster failed: '{run_res.stderr}'")
        raise Exception(f"Cannot bootstrap CAPI")


@pytest.fixture
def flux_environment(flux_app_deployment: ConfiguredApp,
                     gs_crds: Callable[[Cluster], Iterable[Any]],
                     capi_controllers: Callable[[], None]) -> ConfiguredApp:
    return flux_app_deployment


@pytest.mark.smoke
def test_dummy(flux_app_deployment: Callable[[AppFactoryFunc], ConfiguredApp]) -> None:
    print("good")
    pass
