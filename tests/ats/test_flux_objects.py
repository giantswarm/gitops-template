import logging
import os.path
import re
import time
from typing import Any, Callable, Collection, Optional, Type, Union

import pykube
import pytest
import yaml
from deepdiff import DeepDiff
from deepdiff.helper import NotPresent
from pykube.objects import APIObject
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.git_repository import GitRepositoryCR
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.helm_repository import HelmRepositoryCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from pytest_helm_charts.flux.utils import NamespacedFluxCR

from conftest import GitOpsTestConfig

# The checks below follow the spec in
#  https://github.com/giantswarm/gitops-template/issues/219: the row names (H1, R2, ...)
#  in the comments are the ones of its tables.


class OCIRepositoryCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "ocirepositories"
    kind = "OCIRepository"


class HelmChartCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "helmcharts"
    kind = "HelmChart"


class BucketCR(NamespacedFluxCR):
    version = "source.toolkit.fluxcd.io/v1"
    endpoint = "buckets"
    kind = "Bucket"


# The kinds a HelmRelease takes its chart from: `chartRef` names an OCIRepository or a
#  HelmChart, `chart.spec.sourceRef` one of the others.
CHART_SOURCE_KINDS: dict[str, Type[APIObject]] = {
    "OCIRepository": OCIRepositoryCR,
    "HelmChart": HelmChartCR,
    "HelmRepository": HelmRepositoryCR,
    "GitRepository": GitRepositoryCR,
    "Bucket": BucketCR,
}
REFERENCED_KINDS: dict[str, Type[APIObject]] = {
    **CHART_SOURCE_KINDS,
    "ConfigMap": pykube.ConfigMap,
    "Secret": pykube.Secret,
    "HelmRelease": HelmReleaseCR,
}
# S1: the Flux sources that have to get ready, every source kind
SOURCE_KINDS: list[Type[APIObject]] = list(CHART_SOURCE_KINDS.values())
# H2: Giant Swarm's charts that create a workload cluster
CLUSTER_CHART_NAME = re.compile(r"release-(aws|azure|vsphere|cloud-director)")

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
# sources pull from a remote registry or repository, give them more time
SOURCES_READY_TIMEOUT_SEC = 180
# HelmReleases wait for their dependencies, pull images and run hook Jobs. Longer than the
#  examples' `timeout` of 10m, so a release that doesn't get ready reports helm-controller's
#  reason, such as the resources it waited for, instead of being caught mid-install.
HELM_RELEASES_READY_TIMEOUT_SEC = 720
# workloads in the workload cluster, once their HelmReleases are ready
WORKLOADS_AVAILABLE_TIMEOUT_SEC = 120
FLUX_MANAGED_OBJECTS_READY_TIMEOUT_SEC = 15
POLL_INTERVAL_SEC = 5
ASSERTIONS_DIR = "assertions"
EXISTS_ASSERTIONS_DIR = os.path.join(ASSERTIONS_DIR, "exists")
# objects expected in the workload cluster the test's vCluster stands in for
WORKLOAD_CLUSTER_ASSERTIONS_DIR = os.path.join(
    ASSERTIONS_DIR, "exists-in-workload-cluster"
)

# (kind, namespace, name) -> the object, or None if it doesn't exist
Lookup = Callable[[str, str, str], Optional[dict]]

logger = logging.getLogger(__name__)


def obj_key(obj: dict) -> str:
    return f"{obj['metadata'].get('namespace', '')}/{obj['metadata']['name']}"


def condition_true(obj: dict, condition_type: str) -> bool:
    conditions = (obj.get("status") or {}).get("conditions") or []
    return any(
        c.get("type") == condition_type and c.get("status") == "True"
        for c in conditions
    )


def is_ready(obj: dict) -> bool:
    """Whether a Flux object is Ready.

    pytest_helm_charts' `flux_cr_ready` rule, for an object rather than an API object, and
    without its warning on every poll: Flux keeps Ready as the first condition, so that one
    has to be Ready and True.
    """
    conditions = (obj.get("status") or {}).get("conditions") or []
    return (
        bool(conditions)
        and conditions[0].get("type") == "Ready"
        and conditions[0].get("status") == "True"
    )


def not_ready_reason(obj: dict) -> str:
    """Why `is_ready` says no: the first condition, which is the one it reads."""
    conditions = (obj.get("status") or {}).get("conditions") or []
    if not conditions:
        return "has no conditions"
    first = conditions[0]
    return f"{first.get('type')} is {first.get('status')}: {first.get('message', '')}"


def ready(kind: str, obj: dict) -> bool:
    """`is_ready`, except for an OCI HelmRepository: Flux doesn't reconcile one, so it has no
    Ready condition and only has to exist (S1)."""
    oci_helm_repository = (
        kind == "HelmRepository" and (obj.get("spec") or {}).get("type") == "oci"
    )
    return oci_helm_repository or is_ready(obj)


def list_objects(
    api: pykube.HTTPClient, obj_type: Type[APIObject], ignored: Collection[str]
) -> dict[str, dict]:
    """Every `obj_type` object in the cluster by `namespace/name`, except the ignored ones."""
    objects = (o.obj for o in obj_type.objects(api).filter(namespace=pykube.all))
    return {obj_key(o): o for o in objects if obj_key(o) not in ignored}


def wait_for_ready(
    api: pykube.HTTPClient,
    obj_type: Type[APIObject],
    keys: Collection[str],
    timeout_sec: int,
) -> dict[str, str]:
    """Wait for the Flux objects in `keys` to be Ready.

    Returns `namespace/name` -> reason for the ones that aren't Ready when `timeout_sec` is up.
    """
    deadline = time.time() + timeout_sec
    while True:
        current = list_objects(api, obj_type, ())
        not_ready = {
            k: (
                not_ready_reason(current[k])
                if k in current
                else "doesn't exist any more"
            )
            for k in sorted(keys)
            if k not in current or not ready(obj_type.kind, current[k])
        }
        if not not_ready or time.time() >= deadline:
            return not_ready
        logger.debug(
            f"Waiting for {len(not_ready)} {obj_type.kind} objects to be ready: "
            f"{sorted(not_ready)}"
        )
        time.sleep(POLL_INTERVAL_SEC)


def fail_on_problems(problems: list[str], what: str) -> None:
    if problems:
        for p in problems:
            logger.error(p)
        pytest.fail(f"{len(problems)} {what}:\n" + "\n".join(problems))


def check_kustomizations(api: pykube.HTTPClient) -> None:
    """K1: every Kustomization gets ready, including the ones GITOPS_IGNORED_OBJECTS names.
    E2: there has to be one."""
    waited: set[str] = set()
    # The root Kustomizations create the cluster ones once they're ready, so list again
    #  until no new one appears. Otherwise the later checks could run before Flux has
    #  applied what the cluster Kustomizations create.
    while True:
        new = set(list_objects(api, KustomizationCR, ())) - waited
        if not new:
            break
        waited |= new
        not_ready = wait_for_ready(
            api, KustomizationCR, new, FLUX_OBJECTS_READY_TIMEOUT_SEC
        )
        fail_on_problems(
            [f"Kustomization '{k}' isn't ready: {r}" for k, r in not_ready.items()],
            "Kustomizations aren't ready",
        )
    if not waited:
        pytest.fail("There is no Kustomization in the cluster.")
    logger.info(f"{len(waited)} Kustomizations are ready.")


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None
) -> None:
    check_kustomizations(kube_cluster.kube_client)


def test_kustomizations_successful(check_kustomizations_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def check_sources(api: pykube.HTTPClient, ignored: Collection[str]) -> None:
    """S1: every source of every kind that isn't ignored gets ready. E1: none is fine."""
    problems = []
    for kind in SOURCE_KINDS:
        sources = list_objects(api, kind, ignored)
        if not sources:
            logger.info(f"There is no {kind.kind} to check.")
            continue
        not_ready = wait_for_ready(api, kind, sources, SOURCES_READY_TIMEOUT_SEC)
        problems += [
            f"{kind.kind} '{k}' isn't ready: {r}" for k, r in not_ready.items()
        ]
        logger.info(f"Checked {len(sources)} {kind.kind} objects.")
    fail_on_problems(problems, "sources aren't ready")


@pytest.fixture(scope="module")
def check_sources_successful(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
    gitops_test_config: GitOpsTestConfig,
) -> None:
    check_sources(kube_cluster.kube_client, gitops_test_config.ignored_objects)


def test_sources_successful(check_sources_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def cluster_lookup(api: pykube.HTTPClient) -> Lookup:
    """Get objects from the cluster, each one once."""
    found: dict[tuple[str, str, str], Optional[dict]] = {}

    def lookup(kind: str, namespace: str, name: str) -> Optional[dict]:
        if (kind, namespace, name) not in found:
            obj = (
                REFERENCED_KINDS[kind]
                .objects(api)
                .filter(namespace=namespace)
                .get_or_none(name=name)
            )
            found[(kind, namespace, name)] = obj.obj if obj else None
        return found[(kind, namespace, name)]

    return lookup


def chart_source(hr: dict) -> Optional[tuple[str, str, str]]:
    """`(kind, namespace, name)` of the `chartRef`, or else the `chart.spec.sourceRef`."""
    spec = hr["spec"]
    ref = spec.get("chartRef") or ((spec.get("chart") or {}).get("spec") or {}).get(
        "sourceRef"
    )
    if not ref:
        return None
    return (
        ref.get("kind", ""),
        ref.get("namespace", hr["metadata"]["namespace"]),
        ref.get("name", ""),
    )


def chart_name(hr: dict, lookup: Lookup) -> Optional[str]:
    """The name of the chart the HelmRelease installs, if the test can tell.

    `chart.spec.chart` names it. For a `chartRef`, the OCIRepository's URL or the HelmChart's
    `chart` does.
    """
    chart = ((hr["spec"].get("chart") or {}).get("spec") or {}).get("chart")
    if chart:
        return chart.rstrip("/").rsplit("/", 1)[-1]
    source = chart_source(hr)
    if source is None or source[0] not in ("OCIRepository", "HelmChart"):
        return None
    obj = lookup(*source)
    if obj is None:
        return None
    field = "url" if source[0] == "OCIRepository" else "chart"
    return obj["spec"].get(field, "").rstrip("/").rsplit("/", 1)[-1] or None


def kubeconfig_secret(hr: dict) -> Optional[str]:
    return ((hr["spec"].get("kubeConfig") or {}).get("secretRef") or {}).get("name")


def classify(hr: dict, lookup: Lookup) -> str:
    """Which of H1, H2, H3a and H3b the HelmRelease is.

    A workload-cluster app is H3a when its kubeconfig Secret exists in the test cluster,
    whatever the cluster is called.
    """
    name = chart_name(hr, lookup)
    if name is not None and CLUSTER_CHART_NAME.fullmatch(name):
        return "H2"
    if not hr["spec"].get("kubeConfig"):
        return "H1"
    secret = kubeconfig_secret(hr)
    if secret and lookup("Secret", hr["metadata"]["namespace"], secret) is not None:
        return "H3a"
    return "H3b"


def management_cluster_objects(hr: dict) -> set[str]:
    """R3: `<cluster>-kubeconfig` and `<cluster>-cluster-values`, for a kubeconfig Secret
    named `<cluster>-kubeconfig`. The management cluster creates both."""
    secret = kubeconfig_secret(hr) or ""
    if not secret.endswith("-kubeconfig"):
        return set()
    return {secret, f"{secret.removesuffix('-kubeconfig')}-cluster-values"}


def chart_source_key(hr: dict) -> Optional[str]:
    source = chart_source(hr)
    return f"{source[1]}/{source[2]}" if source else None


def chart_source_problems(
    hr: dict, lookup: Lookup, ignored: Collection[str]
) -> list[str]:
    """R1: the chart source has to exist. An ignored one isn't looked up (H4)."""
    source = chart_source(hr)
    if source is None:
        return ["has neither chartRef nor chart.spec.sourceRef"]
    if chart_source_key(hr) in ignored:
        return []
    if source[0] not in CHART_SOURCE_KINDS:
        return [f"chart source kind '{source[0]}' isn't a Flux source"]
    if lookup(*source) is None:
        return [f"chart source {source[0]} '{source[1]}/{source[2]}' doesn't exist"]
    return []


def values_from_problems(hr: dict, exempt: set[str], lookup: Lookup) -> list[str]:
    """R2: every `valuesFrom` object that isn't optional or exempt, and its key, have to exist.

    The content isn't parsed.
    """
    problems = []
    for ref in hr["spec"].get("valuesFrom") or []:
        kind, name = ref.get("kind", ""), ref.get("name", "")
        if ref.get("optional") or name in exempt:
            continue
        obj = (
            lookup(kind, hr["metadata"]["namespace"], name)
            if kind in ("ConfigMap", "Secret")
            else None
        )
        key = ref.get("valuesKey", "values.yaml")
        if obj is None:
            problems.append(f"valuesFrom {kind} '{name}' doesn't exist")
        elif key not in {**(obj.get("data") or {}), **(obj.get("binaryData") or {})}:
            problems.append(f"valuesFrom {kind} '{name}' has no key '{key}'")
    return problems


def reference_problems(
    hr: dict, hr_class: str, lookup: Lookup, ignored: Collection[str] = ()
) -> list[str]:
    """R1-R4: what the HelmRelease refers to has to exist."""
    namespace = hr["metadata"]["namespace"]
    # R3
    exempt = management_cluster_objects(hr) if hr_class == "H3b" else set()
    problems = chart_source_problems(hr, lookup, ignored)

    secret = kubeconfig_secret(hr)
    if (
        hr["spec"].get("kubeConfig")
        and secret not in exempt
        and (not secret or lookup("Secret", namespace, secret) is None)
    ):
        problems.append(f"kubeConfig Secret '{secret}' doesn't exist")

    problems += values_from_problems(hr, exempt, lookup)

    # R4
    for dep in depends_on_keys(hr):
        dep_namespace, _, dep_name = dep.partition("/")
        if lookup("HelmRelease", dep_namespace, dep_name) is None:
            problems.append(f"dependsOn HelmRelease '{dep}' doesn't exist")
    return problems


def depends_on_keys(hr: dict) -> list[str]:
    """`namespace/name` of each HelmRelease in `dependsOn`; the namespace defaults to the HelmRelease's."""
    namespace = hr["metadata"]["namespace"]
    return [
        f"{d.get('namespace', namespace)}/{d['name']}"
        for d in hr["spec"].get("dependsOn") or []
    ]


def helm_releases_to_wait_for(
    hrs: dict[str, dict], classes: dict[str, str], ignored: Collection[str]
) -> set[str]:
    """H1 and H3a, except H5: the ones whose `dependsOn` chain reaches an H2, H3b or H4, or
    whose chart source is ignored."""
    dependents: dict[str, list[str]] = {}
    for key, hr in hrs.items():
        for dep in depends_on_keys(hr):
            dependents.setdefault(dep, []).append(key)
    # walk from the HelmReleases that can't get ready to everything that depends on them
    blocked = (
        {k for k, c in classes.items() if c in ("H2", "H3b")}
        | {k for k, hr in hrs.items() if chart_source_key(hr) in ignored}
        | set(ignored)
    )
    pending = list(blocked)
    while pending:
        for dependent in dependents.get(pending.pop(), []):
            if dependent not in blocked:
                blocked.add(dependent)
                pending.append(dependent)
    return {k for k, c in classes.items() if c in ("H1", "H3a") and k not in blocked}


def check_helm_releases(
    api: pykube.HTTPClient, ignored: Collection[str]
) -> dict[str, dict]:
    """H1-H5 and R1-R4. Returns every H3a HelmRelease, by `namespace/name`, for W1.

    The references are checked before the wait, so a missing one fails at once instead of
    after the wait for the releases that can't get ready without it.
    """
    # H4: the ignored ones aren't looked at at all
    hrs = list_objects(api, HelmReleaseCR, ignored)
    if not hrs:
        logger.info("There is no HelmRelease to check.")
        return {}

    lookup = cluster_lookup(api)
    classes = {k: classify(hr, lookup) for k, hr in hrs.items()}
    for k in sorted(hrs):
        logger.info(f"HelmRelease '{k}': {classes[k]}")
    fail_on_problems(
        [
            f"HelmRelease '{k}': {p}"
            for k in sorted(hrs)
            for p in reference_problems(hrs[k], classes[k], lookup, ignored)
        ],
        f"reference problems in {len(hrs)} HelmReleases",
    )

    to_wait = helm_releases_to_wait_for(hrs, classes, ignored)
    logger.info(f"Waiting for {len(to_wait)} HelmReleases: {sorted(to_wait)}")
    not_ready = wait_for_ready(
        api, HelmReleaseCR, to_wait, HELM_RELEASES_READY_TIMEOUT_SEC
    )
    fail_on_problems(
        [f"HelmRelease '{k}' isn't ready: {r}" for k, r in not_ready.items()],
        "HelmReleases aren't ready",
    )
    return {k: hr for k, hr in hrs.items() if classes[k] == "H3a"}


@pytest.fixture(scope="module")
def check_helm_release_successful(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
    gitops_test_config: GitOpsTestConfig,
) -> dict[str, dict]:
    return check_helm_releases(
        kube_cluster.kube_client, gitops_test_config.ignored_objects
    )


def test_helm_release_successful(check_helm_release_successful: dict) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid duplication in other tests
    pass


def test_positive_assertions(
    kube_cluster: Cluster,
    gitops_deployment: None,
    check_helm_release_successful: dict,
    check_kustomizations_successful: None,
) -> None:
    checked = check_assertions(kube_cluster.kube_client, load_assertions())
    assert checked > 0, f"No assertions found in '{EXISTS_ASSERTIONS_DIR}'."


def deployment_available(obj: dict) -> bool:
    return condition_true(obj, "Available")


def releases_without_assertion(
    releases: dict[str, dict], assertions: list[dict]
) -> list[str]:
    """W1: the releases no assertion names in its `helmRelease` key (`namespace/name` of the
    HelmRelease whose main workload the object is). The key isn't a field of the object, so
    the comparison skips it."""
    asserted = {a.get("helmRelease") for a in assertions}
    return sorted(k for k in releases if k not in asserted)


def test_workload_cluster_assertions(
    workload_cluster: pykube.HTTPClient,
    check_kustomizations_successful: None,
    check_helm_release_successful: dict[str, dict],
) -> None:
    # The -direct out-of-band Kustomization and the H3a HelmReleases install into the
    #  workload cluster through its kubeconfig Secret; the test's vCluster stands in for it.
    assertions = load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR)
    checked = check_assertions(workload_cluster, assertions)
    assert checked > 0, f"No assertions found in '{WORKLOAD_CLUSTER_ASSERTIONS_DIR}'."

    # W1: every H3a release has an assertion of its main workload
    all_assertions = [
        a for file_assertions in assertions.values() for a in file_assertions
    ]
    missing = releases_without_assertion(check_helm_release_successful, all_assertions)
    assert not missing, (
        f"H3a HelmReleases without an assertion of their main workload, one with "
        f"`helmRelease: <namespace>/<name>`, in '{WORKLOAD_CLUSTER_ASSERTIONS_DIR}': {missing}"
    )

    # W1: the Deployments the assertions name have to be available, too
    deployments = [a for a in all_assertions if a.get("kind") == "Deployment"]
    deadline = time.time() + WORKLOADS_AVAILABLE_TIMEOUT_SEC
    while True:
        unavailable = [
            obj_key(d)
            for d in deployments
            if not deployment_available(
                pykube.Deployment.objects(workload_cluster)
                .filter(namespace=d["metadata"]["namespace"])
                .get(name=d["metadata"]["name"])
                .obj
            )
        ]
        if not unavailable or time.time() >= deadline:
            break
        time.sleep(POLL_INTERVAL_SEC)
    assert (
        not unavailable
    ), f"Deployments in the workload cluster aren't available: {unavailable}"


def check_assertions(api: pykube.HTTPClient, assertions: dict[str, list[dict]]) -> int:
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
            endpoint = resource_name(api.resource_list(ass["apiVersion"]), ass["kind"])
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


def load_assertions(
    assertions_dir: str = EXISTS_ASSERTIONS_DIR,
) -> dict[str, list[dict]]:
    """The objects in each `.yaml` file under `assertions_dir`, by file."""
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
                assertions[rel_path] = [d for d in yaml.safe_load_all(f) if d]
    return assertions


def resource_name(resource_list: dict, kind: str) -> str:
    """The plural resource name of `kind`, from the API server's discovery document of its
    group and version (`/api/v1` or `/apis/<group>/<version>`)."""
    for resource in resource_list.get("resources") or []:
        # subresources, such as `deployments/status`, have the kind of their parent
        if resource.get("kind") == kind and "/" not in resource["name"]:
            return resource["name"]
    raise Exception(
        f"The API server doesn't serve kind '{kind}' in "
        f"'{resource_list.get('groupVersion')}'."
    )


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
