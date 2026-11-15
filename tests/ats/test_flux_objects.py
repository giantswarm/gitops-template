import base64
import binascii
import logging
import os.path
import time
from typing import Any, Iterator, Optional, Protocol, Type, TypeVar, Union

import pykube
import pytest
import yaml
from deepdiff import DeepDiff
from deepdiff.helper import NotPresent
from pykube.objects import APIObject
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR

from conftest import GitOpsTestConfig

TFNS = TypeVar("TFNS", bound=NamespacedFluxCR)


class OCIRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "ocirepositories"
    kind = "OCIRepository"


class HelmRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "helmrepositories"
    kind = "HelmRepository"


class GitRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "gitrepositories"
    kind = "GitRepository"


class BucketCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "buckets"
    kind = "Bucket"


class HelmChartCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "helmcharts"
    kind = "HelmChart"


# The kinds a HelmRelease refers to, by the `kind` its references use.
REFERENCED_KINDS: dict[str, Type[APIObject]] = {
    "ConfigMap": pykube.ConfigMap,
    "Secret": pykube.Secret,
    "HelmRelease": HelmReleaseCR,
    "OCIRepository": OCIRepositoryCR,
    "HelmRepository": HelmRepositoryCR,
    "GitRepository": GitRepositoryCR,
    "Bucket": BucketCR,
    "HelmChart": HelmChartCR,
}

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
# OCIRepositories pull charts from a remote registry, give them more time
OCI_REPOSITORIES_READY_TIMEOUT_SEC = 180
FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC = 15
POLL_INTERVAL_SEC = 5
ASSERTIONS_DIR = "assertions"
EXISTS_ASSERTIONS_DIR = os.path.join(ASSERTIONS_DIR, "exists")

logger = logging.getLogger(__name__)


def obj_key(obj: Union[APIObject, dict]) -> str:
    meta = obj.obj["metadata"] if isinstance(obj, APIObject) else obj["metadata"]
    return f"{meta.get('namespace', '')}/{meta['name']}"


def ready_condition(obj: dict) -> Optional[dict]:
    for c in obj.get("status", {}).get("conditions", []):
        if c.get("type") == "Ready":
            return c
    return None


def is_ready(obj: dict) -> bool:
    c = ready_condition(obj)
    return c is not None and c.get("status") == "True"


def list_flux_objects(
    kube_cluster: Cluster, obj_type: Type[TFNS], ignored_objects: list[str]
) -> list[TFNS]:
    return [
        o
        for o in obj_type.objects(kube_cluster.kube_client)
        .filter(namespace=pykube.all)
        .all()
        if obj_key(o) not in ignored_objects
    ]


def parse_inventory_id(entry_id: str) -> Optional[tuple[str, str, str, str]]:
    """Return `(group, kind, namespace, name)` of a Kustomization inventory entry.

    kustomize-controller writes each entry as `<namespace>_<name>_<group>_<kind>`. The namespace
    is empty for cluster-scoped objects, the group for core ones. Neither part can hold a `_`.
    """
    parts = entry_id.split("_")
    if len(parts) != 4:
        return None
    namespace, name, group, kind = parts
    return group, kind, namespace, name


def inventory_objects(
    kustomizations: list[dict], obj_type: Type[APIObject], ignored_objects: list[str]
) -> set[str]:
    """`namespace/name` of every `obj_type` object the Kustomizations applied to this cluster.

    A Kustomization lists what it applied in `status.inventory`. The ones with a `kubeConfig`
    apply to another cluster, and the ignored ones may have failed before they applied
    anything, so their inventories are left out.
    """
    group = obj_type.version.split("/")[0]
    found: set[str] = set()
    for ks in kustomizations:
        if ks.get("spec", {}).get("kubeConfig") or obj_key(ks) in ignored_objects:
            continue
        entries = (ks.get("status", {}).get("inventory") or {}).get("entries") or []
        for entry in entries:
            parsed = parse_inventory_id(entry.get("id", ""))
            if parsed and parsed[0] == group and parsed[1] == obj_type.kind:
                found.add(f"{parsed[2]}/{parsed[3]}")
    return found - set(ignored_objects)


def wait_for_objects_to_exist(
    kube_cluster: Cluster,
    obj_type: Type[TFNS],
    ignored_objects: list[str],
    expected: set[str],
    timeout_sec: int,
) -> list[TFNS]:
    """Wait for every object in `expected` (`namespace/name`) to exist; return all `obj_type` objects."""
    logger.info(f"The Kustomizations applied {len(expected)} {obj_type.kind} objects.")
    deadline = time.time() + timeout_sec
    while True:
        objects = list_flux_objects(kube_cluster, obj_type, ignored_objects)
        missing = expected - {obj_key(o) for o in objects}
        if not missing:
            return objects
        if time.time() >= deadline:
            pytest.fail(
                f"{len(missing)} {obj_type.kind} objects the Kustomizations applied don't exist "
                f"after {timeout_sec} s: {sorted(missing)}"
            )
        time.sleep(POLL_INTERVAL_SEC)


def wait_until_ready(
    kube_cluster: Cluster,
    obj_type: Type[TFNS],
    keys: set[str],
    ignored_objects: list[str],
    timeout_sec: int,
) -> dict[str, str]:
    """Wait for the `obj_type` objects in `keys` to be Ready, listing the kind once per poll.

    Every object is evaluated on every poll, including the last one, so an object that was
    Ready and fails later is reported. Returns `namespace/name` -> reason for the ones that
    aren't Ready when the timeout is reached. A timeout of 0 checks once.
    """
    deadline = time.time() + timeout_sec
    while True:
        current = {
            obj_key(o): o.obj
            for o in list_flux_objects(kube_cluster, obj_type, ignored_objects)
        }
        not_ready: dict[str, str] = {}
        for k in sorted(keys):
            if k not in current:
                not_ready[k] = "doesn't exist any more"
            elif not is_ready(current[k]):
                c = ready_condition(current[k]) or {}
                not_ready[k] = c.get("message") or "has no Ready condition"
        if not not_ready or time.time() >= deadline:
            return not_ready
        logger.debug(
            f"Waiting for {len(not_ready)} {obj_type.kind} objects to be ready: "
            f"{sorted(not_ready)}"
        )
        time.sleep(POLL_INTERVAL_SEC)


def fail_not_ready(obj_type: Type[APIObject], not_ready: dict[str, str]) -> None:
    if not_ready:
        problems = [
            f"{obj_type.kind} '{k}' isn't ready: {r}" for k, r in not_ready.items()
        ]
        for p in problems:
            logger.error(p)
        pytest.fail(
            f"{len(problems)} {obj_type.kind} objects aren't ready:\n"
            + "\n".join(problems)
        )


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None, gitops_test_config: GitOpsTestConfig
) -> list[dict]:
    """Wait for every Kustomization to be ready, and return them with their inventories.

    The test applies the root Kustomizations itself, so at least one has to show up. They
    create the cluster Kustomizations once they're ready, so the check lists the
    Kustomizations again after each wait until no new one appears.
    """
    ignored = gitops_test_config.ignored_objects
    deadline = time.time() + FLUX_OBJECTS_READY_TIMEOUT_SEC
    objects = list_flux_objects(kube_cluster, KustomizationCR, ignored)
    while not objects and time.time() < deadline:
        time.sleep(POLL_INTERVAL_SEC)
        objects = list_flux_objects(kube_cluster, KustomizationCR, ignored)
    if not objects:
        pytest.fail(
            f"No Kustomization showed up in the cluster in {FLUX_OBJECTS_READY_TIMEOUT_SEC} s."
        )

    waited: set[str] = set()
    while True:
        new = {obj_key(o) for o in objects} - waited
        if not new:
            break
        waited |= new
        fail_not_ready(
            KustomizationCR,
            wait_until_ready(
                kube_cluster,
                KustomizationCR,
                new,
                ignored,
                FLUX_OBJECTS_READY_TIMEOUT_SEC,
            ),
        )
        objects = list_flux_objects(kube_cluster, KustomizationCR, ignored)
    # Check them all once more: one that was ready early may have failed since.
    fail_not_ready(
        KustomizationCR,
        wait_until_ready(kube_cluster, KustomizationCR, waited, ignored, 0),
    )
    logger.info(f"{len(waited)} Kustomizations are ready.")
    return [
        o.obj
        for o in KustomizationCR.objects(kube_cluster.kube_client)
        .filter(namespace=pykube.all)
        .all()
    ]


def test_kustomizations_successful(check_kustomizations_successful: list[dict]) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


class ObjectLookup(Protocol):
    def get(self, kind: str, namespace: str, name: str) -> Optional[dict]:
        """The object of `kind` named `namespace/name`, or None if it doesn't exist."""


class ClusterIndex:
    """Every object of a kind, listed once across all namespaces and looked up by name.

    Getting each referenced object on its own takes over a hundred calls for the template's 37
    HelmReleases; listing each kind once takes a handful.
    """

    def __init__(self, kube_client: pykube.HTTPClient) -> None:
        self._client = kube_client
        self._objects: dict[str, dict[tuple[str, str], dict]] = {}

    def get(self, kind: str, namespace: str, name: str) -> Optional[dict]:
        if kind not in self._objects:
            self._objects[kind] = self._list(kind)
        return self._objects[kind].get((namespace, name))

    def _list(self, kind: str) -> dict[tuple[str, str], dict]:
        try:
            objects = (
                REFERENCED_KINDS[kind]
                .objects(self._client)
                .filter(namespace=pykube.all)
                .all()
            )
            return {(o.namespace, o.name): o.obj for o in objects}
        except pykube.exceptions.HTTPError as e:
            # the kind's CRD isn't installed, so none exists
            if e.code == 404:
                return {}
            raise


def is_cluster_chart(hr: dict, index: ObjectLookup) -> bool:
    """Whether the HelmRelease creates a workload cluster from a release-<provider> chart."""
    chart_ref = hr["spec"].get("chartRef", {})
    if chart_ref.get("kind") != "OCIRepository":
        return False
    repo = index.get(
        "OCIRepository",
        chart_ref.get("namespace", hr["metadata"]["namespace"]),
        chart_ref.get("name", ""),
    )
    return repo is not None and "/charts/giantswarm/release-" in repo.get(
        "spec", {}
    ).get("url", "")


def needs_workload_cluster(hr: dict, index: ObjectLookup) -> bool:
    """Whether the HelmRelease can't get ready in the test cluster.

    The ones that deploy to a workload cluster through its kubeconfig can't, as the test has no
    workload clusters. Neither can the ones that create a cluster from a release-<provider>
    chart: the chart's resources need the CRDs of a current Cluster API provider and of
    Crossplane, and its values need the management cluster's `managementCluster` and
    `baseDomain`.
    """
    return bool(hr["spec"].get("kubeConfig")) or is_cluster_chart(hr, index)


# Labels that name the workload cluster an app belongs to: Giant Swarm's, which the template
# sets on every app, and Cluster API's.
CLUSTER_NAME_LABELS = ("giantswarm.io/cluster", "cluster.x-k8s.io/cluster-name")


def workload_cluster_names(hr: dict) -> set[str]:
    """Names of the workload cluster a HelmRelease deploys to, or nothing if it deploys here.

    Cluster API names the kubeconfig Secret `<cluster>-kubeconfig`, so that name gives the
    cluster when it ends that way. A Secret named otherwise, such as `<cluster>-kubeconfig-admin`,
    doesn't, so the cluster labels on the HelmRelease count too.
    """
    secret_ref = (hr["spec"].get("kubeConfig") or {}).get("secretRef") or {}
    if not secret_ref:
        return set()
    names = set()
    secret = secret_ref.get("name", "")
    if secret.endswith("-kubeconfig"):
        names.add(secret.removesuffix("-kubeconfig"))
    labels = hr["metadata"].get("labels") or {}
    names.update(labels[label] for label in CLUSTER_NAME_LABELS if labels.get(label))
    return names


def management_cluster_values(hr: dict) -> set[str]:
    """Names of the ConfigMaps a management cluster provides and this repository doesn't.

    The management cluster creates `<cluster>-cluster-values` for every workload cluster. An app
    that deploys to a workload cluster reads it first.
    """
    return {f"{c}-cluster-values" for c in workload_cluster_names(hr)}


def values_from_problems(hr: dict, index: ObjectLookup) -> list[str]:
    """Check each `valuesFrom` reference the way helm-controller resolves it.

    A required reference has to exist. Every reference that exists has to have its key. Without
    a `targetPath`, the key has to hold a YAML mapping (or nothing), as helm-controller merges
    it into the values. With one, the key holds a single value set at that path, so any text
    will do.
    """
    problems: list[str] = []
    namespace = hr["metadata"]["namespace"]
    skip = management_cluster_values(hr)
    for ref in hr["spec"].get("valuesFrom", []):
        kind, name = ref["kind"], ref["name"]
        key = ref.get("valuesKey", "values.yaml")
        if kind == "ConfigMap" and name in skip:
            continue
        if kind not in ("ConfigMap", "Secret"):
            problems.append(f"valuesFrom kind '{kind}' isn't a ConfigMap or Secret")
            continue
        obj = index.get(kind, namespace, name)
        if obj is None:
            if not ref.get("optional", False):
                problems.append(f"{kind} '{name}' doesn't exist")
            continue
        data = obj.get("data") or {}
        if key not in data:
            problems.append(f"{kind} '{name}' has no key '{key}'")
            continue
        if ref.get("targetPath"):
            continue
        problem = values_problem(kind, data[key])
        if problem:
            problems.append(f"{kind} '{name}' key '{key}' {problem}")
    return problems


def values_problem(kind: str, value: str) -> Optional[str]:
    """What keeps helm-controller from merging `value` into the values, if anything."""
    try:
        text = (
            base64.b64decode(value, validate=True).decode()
            if kind == "Secret"
            else value
        )
    except (binascii.Error, UnicodeDecodeError) as e:
        return f"isn't base64-encoded text: {e}"
    try:
        values = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return f"isn't valid YAML: {e}"
    if values is not None and not isinstance(values, dict):
        return "isn't a YAML mapping"
    return None


def source_problems(
    kind: str, namespace: str, name: str, index: ObjectLookup
) -> list[str]:
    """The chart source has to exist and, if it reports readiness, be ready.

    An OCI HelmRepository has no status, so it only has to exist.
    """
    source = index.get(kind, namespace, name)
    if source is None:
        return [f"{kind} '{namespace}/{name}' doesn't exist"]
    if ready_condition(source) is not None and not is_ready(source):
        return [f"{kind} '{namespace}/{name}' isn't ready"]
    return []


CHART_REF_KINDS = ("OCIRepository", "HelmChart")
CHART_SOURCE_KINDS = ("HelmRepository", "GitRepository", "Bucket")


def chart_problems(hr: dict, index: ObjectLookup) -> list[str]:
    """Check the chart source of a HelmRelease, given as `chartRef` or as `chart`."""
    spec, namespace = hr["spec"], hr["metadata"]["namespace"]
    chart_ref = spec.get("chartRef")
    if chart_ref:
        kind = chart_ref.get("kind")
        if kind not in CHART_REF_KINDS:
            logger.warning(
                f"HelmRelease '{obj_key(hr)}': chartRef kind '{kind}' isn't checked."
            )
            return []
        return source_problems(
            kind, chart_ref.get("namespace", namespace), chart_ref["name"], index
        )
    source_ref = (spec.get("chart") or {}).get("spec", {}).get("sourceRef")
    if not source_ref:
        return ["has neither chartRef nor chart.spec.sourceRef"]
    kind = source_ref.get("kind")
    if kind not in CHART_SOURCE_KINDS:
        logger.warning(
            f"HelmRelease '{obj_key(hr)}': sourceRef kind '{kind}' isn't checked."
        )
        return []
    return source_problems(
        kind, source_ref.get("namespace", namespace), source_ref["name"], index
    )


def helm_release_problems(hr: dict, index: ObjectLookup) -> list[str]:
    """Check what helm-controller needs from the management cluster to reconcile `hr`."""
    problems = chart_problems(hr, index)
    namespace = hr["metadata"]["namespace"]
    for dep in hr["spec"].get("dependsOn", []):
        dep_ns = dep.get("namespace", namespace)
        if index.get("HelmRelease", dep_ns, dep["name"]) is None:
            problems.append(
                f"dependsOn HelmRelease '{dep_ns}/{dep['name']}' doesn't exist"
            )
    problems.extend(values_from_problems(hr, index))
    return problems


@pytest.fixture(scope="module")
def check_helm_release_successful(
    kube_cluster: Cluster,
    gitops_deployment: None,
    gitops_test_config: GitOpsTestConfig,
    check_kustomizations_successful: list[dict],
    check_oci_repositories_successful: None,
) -> None:
    # HelmReleases that can get ready in the test cluster have to. The others can't (see
    #  needs_workload_cluster), so for every HelmRelease the test checks what helm-controller needs
    #  from the management cluster before it gets to the workload cluster: the chart source, the
    #  HelmReleases it depends on, and the values. A HelmRelease with a problem there can't get
    #  ready, so the problem is reported instead of waiting for it.
    ignored = gitops_test_config.ignored_objects
    expected = inventory_objects(
        check_kustomizations_successful, HelmReleaseCR, ignored
    )
    helm_releases = wait_for_objects_to_exist(
        kube_cluster, HelmReleaseCR, ignored, expected, FLUX_OBJECTS_READY_TIMEOUT_SEC
    )
    if not helm_releases:
        logger.info(
            "The Kustomizations applied no HelmRelease, there is none to check."
        )
        return

    index = ClusterIndex(kube_cluster.kube_client)
    problems: list[str] = []
    to_wait: set[str] = set()
    for hr in helm_releases:
        hr_problems = helm_release_problems(hr.obj, index)
        problems.extend(f"HelmRelease '{obj_key(hr)}': {p}" for p in hr_problems)
        if not hr_problems and not needs_workload_cluster(hr.obj, index):
            to_wait.add(obj_key(hr))
    not_ready = wait_until_ready(
        kube_cluster, HelmReleaseCR, to_wait, ignored, FLUX_OBJECTS_READY_TIMEOUT_SEC
    )
    problems.extend(f"HelmRelease '{k}' isn't ready: {r}" for k, r in not_ready.items())
    logger.info(
        f"Checked the references of {len(helm_releases)} HelmReleases, "
        f"waited for {len(to_wait)} to be ready."
    )
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
    kube_cluster: Cluster,
    gitops_deployment: None,
    gitops_test_config: GitOpsTestConfig,
    check_kustomizations_successful: list[dict],
) -> None:
    # The cluster Kustomizations create the OCIRepositories, so this has to run after they're
    #  ready. Their inventories say which OCIRepositories to expect.
    ignored = gitops_test_config.ignored_objects
    expected = inventory_objects(
        check_kustomizations_successful, OCIRepositoryCR, ignored
    )
    repos = wait_for_objects_to_exist(
        kube_cluster, OCIRepositoryCR, ignored, expected, FLUX_OBJECTS_READY_TIMEOUT_SEC
    )
    if not repos:
        logger.info(
            "The Kustomizations applied no OCIRepository, there is none to check."
        )
        return
    fail_not_ready(
        OCIRepositoryCR,
        wait_until_ready(
            kube_cluster,
            OCIRepositoryCR,
            {obj_key(r) for r in repos},
            ignored,
            OCI_REPOSITORIES_READY_TIMEOUT_SEC,
        ),
    )


def test_oci_repositories_successful(check_oci_repositories_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def test_positive_assertions(
    kube_cluster: Cluster,
    gitops_deployment: None,
    check_helm_release_successful: None,
    check_kustomizations_successful: list[dict],
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
