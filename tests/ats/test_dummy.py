import logging
from typing import Callable

import pytest
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.giantswarm_app_platform.app import AppFactoryFunc, ConfiguredApp
from pytest_helm_charts.k8s.deployment import wait_for_deployments_to_run

FLUX_VERSION = "0.11.0"
FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT: int = 180
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
def gs_crds(kube_cluster: Cluster) -> None:
    yield kube_cluster.kubectl(f"create -f {GS_CRDS_COMMIT_URL}")
    kube_cluster.kubectl(f"delete -f {GS_CRDS_COMMIT_URL}")


@pytest.fixture
def flux_environment(flux_app_deployment: ConfiguredApp) -> ConfiguredApp:
    return flux_app_deployment


@pytest.mark.smoke
def test_dummy(flux_app_deployment: Callable[[AppFactoryFunc], ConfiguredApp]) -> None:
    print("good")
    pass
