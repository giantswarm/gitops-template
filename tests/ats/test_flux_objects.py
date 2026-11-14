import base64
import logging
import os.path
import time
from typing import Any, Callable, Type, TypeVar, Iterator, Union

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

logger = logging.getLogger(__name__)


def list_flux_objects(
    kube_cluster: Cluster, obj_type: Type[TFNS], ignored_objects: list[str]
) -> list[TFNS]:
    return [
        o
        for o in obj_type.objects(kube_cluster.kube_client)
        .filter(namespace=pykube.all)
        .all()
        if f"{o.namespace}/{o.name}" not in ignored_objects
    ]


def check_flux_objects_successful(
    kube_cluster: Cluster,
    obj_type: Type[TFNS],
    ignored_objects: Union[list[str], None] = None,
    timeout_sec: int = FLUX_OBJECTS_READY_TIMEOUT_SEC,
    exclude: Union[Callable[[TFNS], bool], None] = None,
) -> list[TFNS]:
    """Wait for every object of `obj_type` to be ready, and return all of them.

    Objects in `ignored_objects` (`namespace/name`) are left out entirely. Objects `exclude`
    returns True for are returned, but not waited for.

    Flux creates objects while others get ready: the root Kustomizations create the cluster
    Kustomizations, which create the OCIRepositories and HelmReleases. So the check waits
    for objects to show up, and lists them again after each wait until no new one appears.
    It fails if none shows up in `timeout_sec`, so it never passes because it found nothing
    to check.
    """
    if not ignored_objects:
        ignored_objects = []
    deadline = time.time() + timeout_sec
    objects = list_flux_objects(kube_cluster, obj_type, ignored_objects)
    while not objects and time.time() < deadline:
        time.sleep(5)
        objects = list_flux_objects(kube_cluster, obj_type, ignored_objects)
    if not objects:
        pytest.fail(
            f"No {obj_type.__name__} objects showed up in the cluster in {timeout_sec} s."
        )

    checked: dict[str, TFNS] = {}
    while True:
        new = [o for o in objects if f"{o.namespace}/{o.name}" not in checked]
        if not new:
            return list(checked.values())
        for o in new:
            checked[f"{o.namespace}/{o.name}"] = o
        to_wait = [o for o in new if not (exclude and exclude(o))]
        for ns in sorted({o.namespace for o in to_wait}):
            obj_names = [o.name for o in to_wait if o.namespace == ns]
            logger.debug(
                f"Waiting max {timeout_sec} s for the following {obj_type.__name__} objects "
                f"to be ready in '{ns}' namespace: '{obj_names}'."
            )
            wait_for_objects_condition(
                kube_cluster.kube_client,
                obj_type,
                obj_names,
                ns,
                flux_cr_ready,
                timeout_sec,
                missing_ok=False,
            )
        objects = list_flux_objects(kube_cluster, obj_type, ignored_objects)


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


def is_cluster_chart(hr: HelmReleaseCR, kube_cluster: Cluster) -> bool:
    """Whether the HelmRelease creates a workload cluster from a release-<provider> chart."""
    chart_ref = hr.obj["spec"].get("chartRef", {})
    repo = (
        OCIRepositoryCR.objects(kube_cluster.kube_client)
        .filter(namespace=chart_ref.get("namespace", hr.namespace))
        .get_or_none(name=chart_ref.get("name"))
    )
    return repo is not None and "/charts/giantswarm/release-" in repo.obj.get(
        "spec", {}
    ).get("url", "")


def needs_workload_cluster(hr: HelmReleaseCR, kube_cluster: Cluster) -> bool:
    """Whether the HelmRelease can't get ready in the test cluster.

    The ones that deploy to a workload cluster through its kubeconfig can't, as the test has no
    workload clusters. Neither can the ones that create a cluster from a release-<provider>
    chart: the chart's resources need the CRDs of a current Cluster API provider and of
    Crossplane, and its values need the management cluster's `managementCluster` and
    `baseDomain`.
    """
    return bool(hr.obj["spec"].get("kubeConfig")) or is_cluster_chart(hr, kube_cluster)


def management_cluster_values(hr: HelmReleaseCR) -> set[str]:
    """Names of the ConfigMaps a management cluster provides and this repository doesn't.

    The management cluster creates `<cluster>-cluster-values` for every workload cluster. An app
    that deploys to a workload cluster through its `<cluster>-kubeconfig` Secret reads it first.
    """
    secret = hr.obj["spec"].get("kubeConfig", {}).get("secretRef", {}).get("name", "")
    if not secret.endswith("-kubeconfig"):
        return set()
    return {secret.removesuffix("-kubeconfig") + "-cluster-values"}


def values_from_problems(hr: HelmReleaseCR, kube_cluster: Cluster) -> list[str]:
    """Check each `valuesFrom` reference the way helm-controller resolves it.

    A required reference has to exist. Every reference that exists has to have its key, and the
    key has to hold a YAML mapping (or nothing).
    """
    problems: list[str] = []
    skip = management_cluster_values(hr)
    for ref in hr.obj["spec"].get("valuesFrom", []):
        kind, name = ref["kind"], ref["name"]
        key = ref.get("valuesKey", "values.yaml")
        if kind == "ConfigMap" and name in skip:
            continue
        obj_type = {"ConfigMap": pykube.ConfigMap, "Secret": pykube.Secret}[kind]
        obj = (
            obj_type.objects(kube_cluster.kube_client)
            .filter(namespace=hr.namespace)
            .get_or_none(name=name)
        )
        if obj is None:
            if not ref.get("optional", False):
                problems.append(f"{kind} '{name}' doesn't exist")
            continue
        data = obj.obj.get("data", {})
        if key not in data:
            problems.append(f"{kind} '{name}' has no key '{key}'")
            continue
        text = data[key]
        if kind == "Secret":
            text = base64.b64decode(text).decode()
        try:
            values = yaml.safe_load(text)
        except yaml.YAMLError as e:
            problems.append(f"{kind} '{name}' key '{key}' isn't valid YAML: {e}")
            continue
        if values is not None and not isinstance(values, dict):
            problems.append(f"{kind} '{name}' key '{key}' isn't a YAML mapping")
    return problems


def helm_release_problems(hr: HelmReleaseCR, kube_cluster: Cluster) -> list[str]:
    """Check what helm-controller needs from the management cluster to reconcile `hr`."""
    problems: list[str] = []
    spec = hr.obj["spec"]

    chart_ref = spec.get("chartRef")
    if not chart_ref:
        problems.append("has no chartRef")
    elif chart_ref.get("kind") != "OCIRepository":
        problems.append(f"chartRef kind '{chart_ref.get('kind')}' isn't checked")
    else:
        repo = (
            OCIRepositoryCR.objects(kube_cluster.kube_client)
            .filter(namespace=chart_ref.get("namespace", hr.namespace))
            .get_or_none(name=chart_ref["name"])
        )
        if repo is None:
            problems.append(f"OCIRepository '{chart_ref['name']}' doesn't exist")
        elif not flux_cr_ready(repo):
            problems.append(f"OCIRepository '{chart_ref['name']}' isn't ready")

    for dep in spec.get("dependsOn", []):
        dep_ns = dep.get("namespace", hr.namespace)
        dep_hr = (
            HelmReleaseCR.objects(kube_cluster.kube_client)
            .filter(namespace=dep_ns)
            .get_or_none(name=dep["name"])
        )
        if dep_hr is None:
            problems.append(
                f"dependsOn HelmRelease '{dep_ns}/{dep['name']}' doesn't exist"
            )

    problems.extend(values_from_problems(hr, kube_cluster))
    return problems


@pytest.fixture(scope="module")
def check_helm_release_successful(
    kube_cluster: Cluster,
    gitops_deployment: None,
    gitops_test_config: GitOpsTestConfig,
    check_kustomizations_successful: None,
    check_oci_repositories_successful: None,
) -> None:
    # HelmReleases that can get ready in the test cluster have to. The others can't (see
    #  needs_workload_cluster), so for every HelmRelease the test checks what helm-controller needs
    #  from the management cluster before it gets to the workload cluster: the chart source, the
    #  HelmReleases it depends on, and the values.
    helm_releases = check_flux_objects_successful(
        kube_cluster,
        HelmReleaseCR,
        gitops_test_config.ignored_objects,
        exclude=lambda hr: needs_workload_cluster(hr, kube_cluster),
    )
    problems: list[str] = []
    for hr in helm_releases:
        problems.extend(
            f"HelmRelease '{hr.namespace}/{hr.name}': {p}"
            for p in helm_release_problems(hr, kube_cluster)
        )
    logger.info(f"Checked the references of {len(helm_releases)} HelmReleases.")
    if problems:
        for p in problems:
            logger.error(p)
        pytest.fail(
            f"{len(problems)} problems in {len(helm_releases)} HelmReleases:\n"
            + "\n".join(problems)
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


def load_assertions() -> dict[str, Iterator]:
    assertions = {}
    walk_dirs = os.walk(EXISTS_ASSERTIONS_DIR)
    for dir_path, _, filenames in walk_dirs:
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
