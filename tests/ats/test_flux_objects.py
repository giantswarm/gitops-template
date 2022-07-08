import logging
from typing import Type, TypeVar

import pykube
import pytest
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR, _flux_cr_ready
from pytest_helm_charts.utils import wait_for_objects_condition

TFNS = TypeVar("TFNS", bound=NamespacedFluxCR)

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60

logger = logging.getLogger(__name__)


def check_flux_objects_successful(kube_cluster: Cluster, obj_type: Type[TFNS]) -> None:
    namespaces = pykube.Namespace.objects(kube_cluster.kube_client).all()
    for ns in namespaces:
        objects = obj_type.objects(kube_cluster.kube_client).filter(namespace=ns.name).all()
        if len(objects.response['items']) == 0:
            continue
        obj_names = [o.name for o in objects]
        logger.debug(f"Waiting max {FLUX_OBJECTS_READY_TIMEOUT_SEC} s for the following {obj_type.__name__} objects "
                     f"to be ready in '{ns.name}' namespace: '{obj_names}'.")
        wait_for_objects_condition(
            kube_cluster.kube_client,
            obj_type,
            obj_names,
            ns.name,
            _flux_cr_ready,
            FLUX_OBJECTS_READY_TIMEOUT_SEC,
            missing_ok=False,
        )


@pytest.mark.smoke
def test_kustomizations_successful(kube_cluster: Cluster, gitops_environment) -> None:
    check_flux_objects_successful(kube_cluster, KustomizationCR)


@pytest.mark.smoke
def test_helm_release_successful(kube_cluster: Cluster, gitops_environment) -> None:
    check_flux_objects_successful(kube_cluster, HelmReleaseCR)
