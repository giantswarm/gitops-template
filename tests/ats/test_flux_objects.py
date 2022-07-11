import logging
import os.path
from typing import Type, TypeVar

import pykube
import pytest
import yaml
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR, _flux_cr_ready
from pytest_helm_charts.giantswarm_app_platform.app import ConfiguredApp
from pytest_helm_charts.utils import wait_for_objects_condition

TFNS = TypeVar("TFNS", bound=NamespacedFluxCR)

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
ASSERTIONS_DIR = "assertions"
EXISTS_ASSERTIONS_DIR = os.path.join(ASSERTIONS_DIR, "exists")

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


#@pytest.mark.smoke
#def test_kustomizations_successful(kube_cluster: Cluster, gitops_environment: ConfiguredApp) -> None:
#    check_flux_objects_successful(kube_cluster, KustomizationCR)
#
#
#@pytest.mark.smoke
#def test_helm_release_successful(kube_cluster: Cluster, gitops_environment: ConfiguredApp) -> None:
#    check_flux_objects_successful(kube_cluster, HelmReleaseCR)


@pytest.mark.smoke
def test_positive_assertions(kube_cluster: Cluster, gitops_environment: ConfiguredApp) -> None:
    assertions = {}
    for entry in os.scandir(EXISTS_ASSERTIONS_DIR):
        if not entry.is_file() or os.path.splitext(entry.name)[1] != ".yaml":
            logger.debug(f"Ignoring file '{entry.name}' in '{EXISTS_ASSERTIONS_DIR}' as it's not a file or it doesn't "
                         f"have a '.yaml' extension.")
            continue
        with open(entry.path) as f:
            from_file_assertions = yaml.safe_load_all(f.read())
            assertions[entry.path] = from_file_assertions

    for file, assert_list in assertions.items():
        # I'm out names for "assertion" :P
        for ass in assert_list:
            cluster_obj = pykube.objects.APIObject(kube_cluster.kube_client, ass)
            setattr(cluster_obj, "kind", ass["kind"])
            setattr(cluster_obj, "version", ass["apiVersion"])
            endpoint = ass["kind"].lower() + ("es" if ass["kind"][-1] == "s" else "s")
            setattr(cluster_obj, "endpoint", endpoint)
            if "namespace" in ass["metadata"]:
                setattr(cluster_obj, "namespace", ass["metadata"]["namespace"])
            cluster_obj.reload()
            for key in ["metadata", "spec", "status"]:
                if key not in ass:
                    continue
                assert ass[key].items() <= cluster_obj.obj[key].items()
