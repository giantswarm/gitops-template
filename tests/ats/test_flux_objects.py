import logging
import os.path
import time
from typing import Type, TypeVar, Iterator, Union

import pykube
import pytest
import yaml
from deepdiff import DeepDiff
from deepdiff.helper import NotPresent
from pykube.objects import APIObject
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR, flux_cr_ready
from pytest_helm_charts.utils import wait_for_objects_condition

from conftest import GitOpsTestConfig

TFNS = TypeVar("TFNS", bound=NamespacedFluxCR)

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC = 15
ASSERTIONS_DIR = "assertions"
EXISTS_ASSERTIONS_DIR = os.path.join(ASSERTIONS_DIR, "exists")

logger = logging.getLogger(__name__)


def check_flux_objects_successful(
    kube_cluster: Cluster, obj_type: Type[TFNS], ignored_objects: list[str] = None
) -> None:
    namespaces = pykube.Namespace.objects(kube_cluster.kube_client).all()
    for ns in namespaces:
        objects = (
            obj_type.objects(kube_cluster.kube_client).filter(namespace=ns.name).all()
        )
        if not objects.response["items"]:
            continue
        if not ignored_objects:
            ignored_objects = []
        obj_names = [o.name for o in objects if f"{ns}/{o.name}" not in ignored_objects]
        if not obj_names:
            continue
        logger.debug(
            f"Waiting max {FLUX_OBJECTS_READY_TIMEOUT_SEC} s for the following {obj_type.__name__} objects "
            f"to be ready in '{ns.name}' namespace: '{obj_names}'."
        )
        wait_for_objects_condition(
            kube_cluster.kube_client,
            obj_type,
            obj_names,
            ns.name,
            flux_cr_ready,
            FLUX_OBJECTS_READY_TIMEOUT_SEC,
            missing_ok=False,
        )


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None, gitops_test_config: GitOpsTestConfig
) -> None:
    check_flux_objects_successful(
        kube_cluster, KustomizationCR, gitops_test_config.ignored_objects
    )


def test_kustomizations_successful(check_kustomizations_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


@pytest.fixture(scope="module")
def check_helm_release_successful(
    kube_cluster: Cluster, gitops_deployment: None, gitops_test_config: GitOpsTestConfig
) -> None:
    check_flux_objects_successful(
        kube_cluster, HelmReleaseCR, gitops_test_config.ignored_objects
    )


def test_helm_release_successful(check_helm_release_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def test_positive_assertions(
    kube_cluster: Cluster,
    gitops_deployment: None,
    check_helm_release_successful: None,
    check_kustomizations_successful: None,
) -> None:
    assertions = load_assertions()
    for file, assert_list in assertions.items():
        # I'm out names for "assertion" :P
        for ass in assert_list:
            if "metadata" not in ass or "kind" not in ass:
                msg = f"Expected object declared in the '{file}' has to have the 'metadata' and 'kind' properties."
                logger.error(msg)
                raise Exception(msg)
            if "name" not in ass["metadata"]:
                msg = f"Expected object declared in the '{file}' has to have 'name' property in the 'metadata' section."
                logger.error(msg)
                raise Exception(msg)
            if "namespace" in ass["metadata"]:
                cluster_obj = pykube.objects.NamespacedAPIObject(
                    kube_cluster.kube_client, ass
                )
                cluster_obj.obj["metadata"]["namespace"] = ass["metadata"]["namespace"]
            else:
                cluster_obj = pykube.objects.APIObject(kube_cluster.kube_client, ass)
            setattr(cluster_obj, "kind", ass["kind"])
            setattr(cluster_obj, "version", ass["apiVersion"])
            endpoint = get_plural_from_kind(ass["kind"])
            setattr(cluster_obj, "endpoint", endpoint)

            reload_obj_from_cluster(cluster_obj)
            assert_objects(ass, cluster_obj, file)


def reload_obj_from_cluster(
    cluster_obj: Union[pykube.objects.NamespacedAPIObject, pykube.objects.APIObject]
) -> None:
    retries = 0
    obj_loaded = False
    while retries < FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC:
        try:
            cluster_obj.reload()
            obj_loaded = True
            break
        except pykube.http.HTTPError as err:
            # we might need to wait a bit for flux to create all the managed objects
            if err.code != 404:
                raise
            time.sleep(1)
            retries += 1
    if not obj_loaded:
        meta = cluster_obj.obj["metadata"]
        obj_name = (
            meta["namespace"] + "/" + meta["name"]
            if "namespace" in meta
            else meta["name"]
        )
        raise Exception(
            f"Timeout of {FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC} sec reached while waiting "
            + f"for object '{obj_name}' of kind '{cluster_obj.kind}'"
        )


def load_assertions() -> dict[str, Iterator]:
    assertions = {}
    walk_dirs = os.walk(EXISTS_ASSERTIONS_DIR)
    for (dir_path, _, filenames) in walk_dirs:
        for file in filenames:
            rel_path = str(os.path.join(dir_path, file))
            if os.path.splitext(file)[1] != ".yaml":
                logger.debug(
                    f"Ignoring file '{rel_path}' in '{EXISTS_ASSERTIONS_DIR}' as it's not a file or it"
                    f" doesn't have a '.yaml' extension."
                )
                continue
            with open(rel_path) as f:
                from_file_assertions = yaml.safe_load_all(f.read())
                assertions[rel_path] = from_file_assertions
    return assertions


def get_plural_from_kind(kind: str) -> str:
    if kind[-1] == "s":
        endpoint = kind.lower() + "es"
    elif kind[-1] == "y":
        endpoint = kind.lower()[:-1] + "ies"
    else:
        endpoint = kind.lower() + "s"
    return endpoint


def assert_objects(ass: dict, cluster_obj: APIObject, file: str) -> None:
    top_level_keys = cluster_obj.obj.keys()
    for key in top_level_keys:
        if key not in ass:
            continue
        diff = DeepDiff(ass[key], cluster_obj.obj[key], ignore_order=True)
        # we have no difference between the expectation and the real object
        if len(diff) == 0:
            continue
        # The only difference that we allow for is when the real object has some attributes that the
        #  expectation doesn't have. This means that if a diff of a kind different from 'dictionary_item_added'
        #  is detected, it's an error.
        if len(diff) > 1 or "dictionary_item_added" not in diff.tree:
            meta = cluster_obj.obj["metadata"]
            obj_name = (
                meta["namespace"] + "/" + meta["name"]
                if "namespace" in meta
                else meta["name"]
            )
            msg = (
                f"Object '{obj_name}' of kind '{cluster_obj.obj['kind']}' is different than expectation in "
                f"file '{file}'."
            )
            logger.error(msg)
            logger.error(diff)
            pytest.fail(msg)
        # Even if we only have 'dictionary_item_added', it has to show that added stuff is only on the
        #  real object side. In other words, we check that all the attributes given in the expectation
        # are present in the real object.
        for d in diff.tree["dictionary_item_added"].items:
            assert isinstance(d.t1, NotPresent)
