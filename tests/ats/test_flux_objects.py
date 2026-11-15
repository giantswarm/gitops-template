import logging
import os.path
import time
from typing import Any, Type, TypeVar, Iterable, Iterator, Union

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


class OCIRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "ocirepositories"
    kind = "OCIRepository"


FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
# OCIRepositories pull charts from a remote registry, give them more time
OCI_REPOSITORIES_READY_TIMEOUT_SEC = 180
FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC = 15
ASSERTIONS_DIR = "assertions"
EXISTS_ASSERTIONS_DIR = os.path.join(ASSERTIONS_DIR, "exists")
# objects expected in the workload cluster the -direct out-of-band example applies to
WORKLOAD_CLUSTER_ASSERTIONS_DIR = os.path.join(
    ASSERTIONS_DIR, "exists-in-workload-cluster"
)

logger = logging.getLogger(__name__)


def cluster_chart_names(
    kube_cluster: Cluster, namespace: str, helm_releases: Iterable[APIObject]
) -> set[str]:
    """Return the names of the OCIRepositories in `namespace` that serve a release-<provider> chart.

    kustomize-controller applies a HelmRelease shortly before the OCIRepository it refers to, so
    the OCIRepositories can still be missing when the HelmReleases are listed. Wait until every
    OCIRepository a HelmRelease's `chartRef` names exists, so a cluster HelmRelease isn't taken
    for one that has to become ready.
    """
    wanted = {
        hr.obj.get("spec", {}).get("chartRef", {}).get("name")
        for hr in helm_releases
        if hr.obj.get("spec", {}).get("chartRef", {}).get("kind") == "OCIRepository"
    }
    deadline = time.time() + FLUX_OBJECTS_READY_TIMEOUT_SEC
    while True:
        repos = list(
            OCIRepositoryCR.objects(kube_cluster.kube_client)
            .filter(namespace=namespace)
            .all()
        )
        missing = wanted - {r.name for r in repos}
        if not missing or time.time() >= deadline:
            break
        logger.debug(
            f"Waiting for the OCIRepositories {sorted(missing)} in '{namespace}' namespace."
        )
        time.sleep(5)
    return {
        r.name
        for r in repos
        if "/charts/giantswarm/release-" in r.obj.get("spec", {}).get("url", "")
    }


def check_flux_objects_successful(
    kube_cluster: Cluster,
    obj_type: Type[TFNS],
    ignored_objects: Union[list[str], None] = None,
    timeout_sec: int = FLUX_OBJECTS_READY_TIMEOUT_SEC,
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
        # HelmReleases that deploy to a workload cluster through its kubeconfig aren't waited for:
        #  most of the clusters they target don't exist in the test. The test's only workload
        #  cluster is the vCluster behind mapi-out-of-band-no-flux-kubeconfig, and it is checked
        #  through the -direct Kustomization and its assertions. Nor are the ones that create a
        #  cluster from a release-<provider> chart, as the test has no cloud account to create it in.
        #  Their existence
        #  is still checked by the assertions, and their charts by the OCIRepository check.
        cluster_charts = set()
        if obj_type is HelmReleaseCR:
            cluster_charts = cluster_chart_names(kube_cluster, ns.name, objects)
        obj_names = [
            o.name
            for o in objects
            if f"{ns}/{o.name}" not in ignored_objects
            and not (
                obj_type is HelmReleaseCR
                and (
                    o.obj.get("spec", {}).get("kubeConfig")
                    or o.obj.get("spec", {}).get("chartRef", {}).get("name")
                    in cluster_charts
                )
            )
        ]
        if not obj_names:
            continue
        logger.debug(
            f"Waiting max {timeout_sec} s for the following {obj_type.__name__} objects "
            f"to be ready in '{ns.name}' namespace: '{obj_names}'."
        )
        wait_for_objects_condition(
            kube_cluster.kube_client,
            obj_type,
            obj_names,
            ns.name,
            flux_cr_ready,
            timeout_sec,
            missing_ok=False,
        )


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None, gitops_test_config: GitOpsTestConfig
) -> None:
    try:
        # The root Kustomizations create the cluster ones, so check again until no new
        #  Kustomization shows up. Otherwise the later checks can run before Flux has applied
        #  what the cluster Kustomizations create.
        count = 0
        while True:
            check_flux_objects_successful(
                kube_cluster, KustomizationCR, gitops_test_config.ignored_objects
            )
            new_count = len(
                KustomizationCR.objects(kube_cluster.kube_client)
                .filter(namespace=pykube.all)
                .all()
                .response["items"]
            )
            if new_count == count:
                break
            count = new_count
    except TimeoutError:
        # say which Kustomization didn't get ready, and why
        for k in KustomizationCR.objects(kube_cluster.kube_client).filter(
            namespace=pykube.all
        ):
            if not flux_cr_ready(k):
                logger.error(
                    f"Kustomization '{k.namespace}/{k.name}' isn't ready: "
                    f"{k.obj.get('status', {}).get('conditions')}"
                )
        raise


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


@pytest.fixture(scope="module")
def check_oci_repositories_successful(
    kube_cluster: Cluster, gitops_deployment: None, gitops_test_config: GitOpsTestConfig
) -> None:
    check_flux_objects_successful(
        kube_cluster,
        OCIRepositoryCR,
        gitops_test_config.ignored_objects,
        OCI_REPOSITORIES_READY_TIMEOUT_SEC,
    )


def test_oci_repositories_successful(check_oci_repositories_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def test_positive_assertions(
    kube_cluster: Cluster,
    gitops_deployment: None,
    check_helm_release_successful: None,
    check_kustomizations_successful: None,
) -> None:
    checked = check_assertions(kube_cluster.kube_client, load_assertions())
    assert checked > 0, f"No assertions found in '{EXISTS_ASSERTIONS_DIR}'."


def test_workload_cluster_assertions(
    workload_cluster: pykube.HTTPClient,
    check_kustomizations_successful: None,
) -> None:
    # The -direct out-of-band Kustomization applies its manifests to the workload cluster
    #  through its kubeconfig Secret; the test's vCluster stands in for it.
    checked = check_assertions(
        workload_cluster, load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR)
    )
    assert checked > 0, f"No assertions found in '{WORKLOAD_CLUSTER_ASSERTIONS_DIR}'."


def check_assertions(api: pykube.HTTPClient, assertions: dict[str, Iterator]) -> int:
    """Check every assertion against the cluster `api` talks to; return how many there were."""
    checked = 0
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
                cluster_obj = pykube.objects.NamespacedAPIObject(api, ass)
                cluster_obj.obj["metadata"]["namespace"] = ass["metadata"]["namespace"]
            else:
                cluster_obj = pykube.objects.APIObject(api, ass)
            setattr(cluster_obj, "kind", ass["kind"])
            setattr(cluster_obj, "version", ass["apiVersion"])
            endpoint = get_plural_from_kind(ass["kind"])
            setattr(cluster_obj, "endpoint", endpoint)

            reload_obj_from_cluster(cluster_obj)
            assert_objects(ass, cluster_obj, file)
            checked += 1
    return checked


def reload_obj_from_cluster(
    cluster_obj: Union[pykube.objects.NamespacedAPIObject, pykube.objects.APIObject],
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


def load_assertions(assertions_dir: str = EXISTS_ASSERTIONS_DIR) -> dict[str, Iterator]:
    assertions = {}
    walk_dirs = os.walk(assertions_dir)
    for dir_path, _, filenames in walk_dirs:
        for file in filenames:
            rel_path = str(os.path.join(dir_path, file))
            if os.path.splitext(file)[1] != ".yaml":
                logger.debug(
                    f"Ignoring file '{rel_path}' in '{assertions_dir}' as it's not a file or it"
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


def normalize_whitespace(value: Any) -> Any:
    """Return `value` with trailing whitespace removed from every line of every string in it.

    Multi-line strings, such as the `values` of a ConfigMap, are compared as text. Whether an
    assertion file writes them as `|` or `|-`, or a line ends in a stray space, says nothing
    about the values, so those differences are dropped before the comparison. Every other
    difference in the text, including indentation, still fails it.
    """
    if isinstance(value, str):
        return "\n".join(line.rstrip() for line in value.splitlines())
    if isinstance(value, dict):
        return {k: normalize_whitespace(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_whitespace(v) for v in value]
    return value


def _order_matters_not(level: Any) -> bool:
    return "valuesFrom" not in level.path()


def assert_objects(ass: dict, cluster_obj: APIObject, file: str) -> None:
    top_level_keys = cluster_obj.obj.keys()
    for key in top_level_keys:
        if key not in ass:
            continue
        diff = DeepDiff(
            normalize_whitespace(ass[key]),
            normalize_whitespace(cluster_obj.obj[key]),
            # List order doesn't matter, except for `valuesFrom`: Helm merges
            # values in that order, so a reordered list changes the result.
            ignore_order=False,
            ignore_order_func=_order_matters_not,
            threshold_to_diff_deeper=0,
        )
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
        for d in diff.tree["dictionary_item_added"]:
            assert isinstance(d.t1, NotPresent)
