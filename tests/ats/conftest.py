import base64
import copy
import logging
import os
import shutil
import subprocess  # nosec B404 - we need to invoke processes
import tempfile
import time
import urllib.request
from typing import Any, Iterable, NamedTuple

import pykube
import pytest
import requests
import validators
import yaml
from ci_context import GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME
from flux_teardown import delete_without_prune
from kind_config import kind_test_config, require_example
from pykube import Secret
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.git_repository import GitRepositoryFactoryFunc
from pytest_helm_charts.utils import wait_for_objects_condition
from repository_objects import (
    credentials_secret,
    credentials_secret_name,
    decryption_secrets,
)

# ci_context's hooks skip cluster tests on a fork's pull request; kyverno_install and
# flux_install have fixtures; admission_policies applies the platform's Flux admission
# policies; external_secrets installs External Secrets Operator;
# notification_objects suspends the notification example's Alert; automation_rbac gives the
# `automation` ServiceAccounts the rights they have on a management cluster;
# flux_operator_install installs Flux Operator; organization_operator stands in for
# organization-operator, which creates the organisation's namespace once Flux has applied its
# Organization. workload_diagnostics adds the state of the workload cluster and the kind node
# to the report of a test of the workload cluster that fails; pytester tests that hook.
# image_automation decrypts the image automation example's deploy key and sets the branch its
# automation pushes to.
pytest_plugins = [
    "ci_context",
    "kyverno_install",
    "admission_policies",
    "flux_install",
    "external_secrets",
    "notification_objects",
    "automation_rbac",
    "flux_operator_install",
    "image_automation",
    "organization_operator",
    "workload_diagnostics",
    "pytester",
]

FLUX_OBJECTS_NAMESPACE = "default"
# the variable of the workflow's token, which reads the repository when it's private
REPOSITORY_READER_ENV_VAR_NAME = "GITHUB_TOKEN"

# The test cluster has the Cluster API core CRDs (cluster.x-k8s.io and its
# addons, ipam and runtime groups), and nothing else of Cluster API: no
# controllers, no infrastructure providers. This repository doesn't test cluster
# creation; that needs a real management cluster. The CRDs let a test create
# CAPI objects, such as a stand-in Cluster whose status the test sets itself.
# The version is the CAPI of the management clusters: cluster-api-app v9.0.4
# ships CAPI v1.14.4.
# renovate: datasource=github-releases depName=kubernetes-sigs/cluster-api
CAPI_VERSION = "v1.14.4"
CAPI_CORE_COMPONENTS_URL = (
    "https://github.com/kubernetes-sigs/cluster-api/releases/download/"
    f"{CAPI_VERSION}/core-components.yaml"
)

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT_SEC = 180
GS_CRDS_URLS = [
    "https://raw.githubusercontent.com/giantswarm/apiextensions/master/helm/crds-common/templates/"
    + "security.giantswarm.io_organizations.yaml"
]
GITOPS_REPO_DIR = "../.."

HELM_URL = "https://helm.sh/docs/intro/install/"
# A vCluster inside the test cluster stands in for the workload cluster the -direct out-of-band
# example targets. The Secret is the one its Kustomization reads through `spec.kubeConfig.secretRef`.
# The example is the binding of this name in kind-test.yaml: without it, there is no vCluster.
WORKLOAD_CLUSTER_EXAMPLE = "out-of-band-no-flux"
WORKLOAD_CLUSTER_VCLUSTER_NAME = "out-of-band-no-flux"
WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE = "vcluster-out-of-band-no-flux"
VCLUSTER_CHART_REPO = "https://charts.loft.sh"
# renovate: datasource=helm depName=vcluster registryUrl=https://charts.loft.sh
VCLUSTER_CHART_VERSION = "0.37.6"
# The vCluster's Kubernetes: the chart's default for 0.37.6, set here so it doesn't move with the
# chart. Keep it on the Kubernetes minor version of the kind cluster and the management clusters.
# renovate: datasource=docker depName=ghcr.io/loft-sh/kubernetes
VCLUSTER_KUBERNETES_IMAGE_TAG = "v1.36.6"
VCLUSTER_READY_TIMEOUT_SEC = 300
WORKLOAD_CLUSTER_KUBECONFIG_NAME = "out-of-band-no-flux-kubeconfig"
WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE = "org-org-name"
# On a Giant Swarm management cluster, the `cluster-app-installation-values` ConfigMap holds the
# management cluster's values, such as its name and base domain. It exists in the `giantswarm`
# namespace, and the Kyverno policy `sync-cluster-app-configmap-to-org-namespaces` copies it into
# every `org-*` namespace. The cluster HelmReleases read it, so the test creates a stand-in in the
# organisation's namespace once it exists, with the placeholder values validate-helm-values uses.
INSTALLATION_VALUES_CONFIG_MAP_NAME = "cluster-app-installation-values"
INSTALLATION_VALUES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../tools/values-stubs/cluster-app-installation-values.yaml",
)
# The management cluster creates `<cluster>-cluster-values` for every workload cluster, and the
# apps of the cluster read it. The stand-in has the content tools/validate-helm-values renders with.
WORKLOAD_CLUSTER_VALUES_NAME = f"{WORKLOAD_CLUSTER_VCLUSTER_NAME}-cluster-values"
CLUSTER_VALUES_STUB = "../../tools/values-stubs/cluster-values.yaml"
# The CRDs the apps of the workload cluster create objects of, beyond the ones their charts
#  install. A Giant Swarm workload cluster gets them from its default apps; the vCluster gets
#  only the CRDs, as nothing in the test needs the controllers. The README there lists them,
#  where they come from and which app needs them.
WORKLOAD_CLUSTER_CRDS_DIR = "fixtures/crds"
# The PriorityClass the cluster chart creates in every Giant Swarm workload cluster. The
#  envoy-gateway Deployment uses it, and its pods can't be created without it.
WORKLOAD_CLUSTER_PRIORITY_CLASS = {
    "apiVersion": "scheduling.k8s.io/v1",
    "kind": "PriorityClass",
    "metadata": {"name": "giantswarm-critical"},
    "value": 1000000000,
}


class PriorityClass(pykube.objects.APIObject):
    version = "scheduling.k8s.io/v1"
    endpoint = "priorityclasses"
    kind = "PriorityClass"


logger = logging.getLogger(__name__)


def pytest_report_header(config: pytest.Config) -> str:
    """Print the Kubernetes version of the test cluster at the top of the pytest output.

    The kind node image, and so the Kubernetes version, follows the kind release
    the workflow installs, so the log shows which version the suite ran on.
    """
    # The same sources as pytest-helm-charts' kube_config fixture: the
    # --kubeconfig option, then the KUBECONFIG environment variable.
    kube_config = config.getoption("kubeconfig", default=None) or os.getenv(
        "KUBECONFIG"
    )
    if not kube_config:
        return "kubernetes server: unknown (no kube config)"
    # The header must never stop the run.
    try:
        api = pykube.HTTPClient(pykube.KubeConfig.from_file(kube_config))
        response = api.get(version="", base="/version")
        response.raise_for_status()
        server = response.json()
    except Exception as e:
        return f"kubernetes server: unknown ({e})"
    return f"kubernetes server: {server.get('gitVersion')} ({server.get('platform')})"


class GitOpsTestConfig:
    _GITOPS_REPO_URL_ENV_VAR_NAME = "GITOPS_REPO_URL"
    _GITOPS_REPO_BRANCH_ENV_VAR_NAME = "GITOPS_REPO_BRANCH"
    _FLUX_INIT_NAMESPACES_ENV_VAR_NAME = "GITOPS_INIT_NAMESPACES"
    _FLUX_APP_VERSION = "GITOPS_FLUX_APP_VERSION"
    _IGNORED_OBJECTS = "GITOPS_IGNORED_OBJECTS"

    def __init__(self) -> None:
        env_var_namespaces = os.getenv(self._FLUX_INIT_NAMESPACES_ENV_VAR_NAME)
        if env_var_namespaces:
            namespaces = env_var_namespaces.split(",")
        else:
            namespaces = ["default"]
        self.init_namespaces = namespaces

        # needed only when a root Kustomization decrypts, see repository_objects
        self.master_private_key = os.environ.get(GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME, "")
        self.github_token = os.environ.get(REPOSITORY_READER_ENV_VAR_NAME, "")

        self.gitops_repo_url = os.environ[self._GITOPS_REPO_URL_ENV_VAR_NAME]
        if not validators.url(self.gitops_repo_url):
            logger.error(
                f"The '{self._GITOPS_REPO_URL_ENV_VAR_NAME}' environment variable must point to the gitops "
                f"repository you want to run tests for (malformed URL)"
                f" [current value: '{self.gitops_repo_url}']."
            )
            raise Exception("malformed gitops repo URL")

        self.gitops_repo_branch = os.environ[self._GITOPS_REPO_BRANCH_ENV_VAR_NAME]
        if not self.gitops_repo_branch:
            logger.error(
                f"The '{self._GITOPS_REPO_BRANCH_ENV_VAR_NAME}' environment variable must point to a branch "
                f"in the gitops repository configured by '{self.gitops_repo_url}'"
                f" [current value: '{self.gitops_repo_branch}']."
            )
            raise Exception("gitops repo branch name missing")

        self.flux_app_version = os.environ[self._FLUX_APP_VERSION]
        if not self.flux_app_version:
            logger.error(
                f"The '{self._FLUX_APP_VERSION}' environment variable must be set to a valid semver."
            )
            raise Exception("flux-app version not set")

        # empty when every Flux object is expected to get ready
        self.ignored_objects = parse_ignored_objects(
            os.environ.get(self._IGNORED_OBJECTS, "")
        )


def parse_ignored_objects(value: str) -> list[str]:
    """Split the comma-separated `namespace/name` list of GITOPS_IGNORED_OBJECTS."""
    return [o.strip() for o in value.split(",") if o.strip()]


def organization_init_namespaces(namespaces: list[str]) -> list[str]:
    """The organisation namespaces among GITOPS_INIT_NAMESPACES. The test bootstraps the
    repository as a new management cluster does, where only organization-operator creates them,
    once Flux has applied the Organization, so there must be none."""
    return [ns for ns in namespaces if ns.startswith("org-")]


@pytest.fixture(scope="module")
def gitops_test_config() -> GitOpsTestConfig:
    return GitOpsTestConfig()


@pytest.fixture(scope="module")
def gs_crds(kube_cluster: Cluster) -> None:
    logger.debug("Deploying Giant Swarm CRDs to the test cluster")
    for crd in GS_CRDS_URLS:
        kube_cluster.kubectl(f"apply -f {crd}")


@pytest.fixture(scope="module")
def capi_crds(kube_cluster: Cluster) -> None:
    """Install the Cluster API core CRDs, without the controllers.

    The CRDs come from the release's core-components.yaml, which also holds the
    controller Deployment, its RBAC and webhooks; only the CRDs are applied.
    """
    logger.debug(f"Deploying Cluster API {CAPI_VERSION} CRDs to the test cluster")
    with urllib.request.urlopen(  # nosec B310 - a fixed https URL
        CAPI_CORE_COMPONENTS_URL, timeout=60
    ) as response:
        documents = yaml.safe_load_all(response.read())
        crds = [
            doc
            for doc in documents
            if doc and doc.get("kind") == "CustomResourceDefinition"
        ]
    if not crds:
        raise Exception(f"No CRDs found in '{CAPI_CORE_COMPONENTS_URL}'")
    for crd in crds:
        # The CRDs convert between API versions with the CAPI controller's
        # webhook, which doesn't run here. Without it, the API server only
        # changes apiVersion, so every served version still works.
        crd["spec"].pop("conversion", None)
    # Server-side, because the Cluster and ClusterClass CRDs are too big for
    # the last-applied-configuration annotation of a client-side apply.
    kube_cluster.kubectl(
        "apply --server-side",
        std_input=yaml.safe_dump_all(crds),
        output_format="name",
    )
    kube_cluster.kubectl(
        "wait --for=condition=Established --timeout=60s crd"
        " --selector=cluster.x-k8s.io/provider=cluster-api",
        output_format="name",
    )


def installation_values_config_map(
    api: pykube.HTTPClient, namespace: str
) -> pykube.ConfigMap:
    """Return the stand-in for the management cluster's `cluster-app-installation-values`."""
    with open(INSTALLATION_VALUES_FILE) as f:
        values = f.read()
    return pykube.ConfigMap(
        api,
        {
            "metadata": {
                "name": INSTALLATION_VALUES_CONFIG_MAP_NAME,
                "namespace": namespace,
            },
            "data": {"values.yaml": values},
        },
    )


@pytest.fixture(scope="module")
def init_namespaces(
    kube_cluster: Cluster, gitops_test_config: GitOpsTestConfig
) -> Iterable[Any]:
    """Create the namespaces of GITOPS_INIT_NAMESPACES that don't exist; fail if it names an
    organisation namespace, which organization_operator creates.

    The `automation` ServiceAccounts in them, and their rights, come from the
    `automation_rbac` fixture, once every CRD of the test is installed.
    """
    refused = organization_init_namespaces(gitops_test_config.init_namespaces)
    if refused:
        pytest.fail(
            f"GITOPS_INIT_NAMESPACES names organisation namespaces, {refused}: the test "
            "creates them after Flux has applied the Organization, as organization-operator does"
        )
    created_namespaces: list[pykube.Namespace] = []

    for ns in gitops_test_config.init_namespaces:
        ns_on_cluster = pykube.Namespace.objects(kube_cluster.kube_client).get_or_none(
            name=ns
        )
        if not ns_on_cluster:
            new_ns = pykube.Namespace(
                kube_cluster.kube_client, {"metadata": {"name": ns}}
            )
            new_ns.create()
            created_namespaces.append(new_ns)

    yield

    for namespace in created_namespaces:
        namespace.delete()


@pytest.fixture(scope="module")
def gpg_master_key(
    kube_cluster: Cluster, gitops_test_config: GitOpsTestConfig
) -> Iterable[list[Secret]]:
    """Create the Secret each root Kustomization decrypts with, from GITOPS_MASTER_GPG_KEY, as you
    apply it by hand on a new management cluster. Flux keeps it up to date afterwards.
    """
    secrets = [
        pykube.Secret(kube_cluster.kube_client, s)
        for s in decryption_secrets(
            kind_test_config().decryption_secrets(),
            gitops_test_config.master_private_key,
        )
    ]
    for secret in secrets:
        secret.create()

    yield secrets

    for secret in secrets:
        secret.delete()


def run_tool(name: str, url: str, *args: str) -> str:
    """Run `name` from the $PATH with `args`, and return its output.

    It fails if the tool isn't in the $PATH, saying to install it from `url`, or if it fails.
    """
    path = shutil.which(name)
    if not path:
        logger.error(
            f"You must install `{name}` from '{url}' and make it available in your $PATH."
        )
        raise Exception(f"`{name}` not found")
    logger.debug(f"Running '{path}' with {list(args)}")
    run_res = subprocess.run(  # nosec B603 - fixed arguments, no user input
        [path, *args], capture_output=True, text=True
    )
    if run_res.returncode != 0:
        logger.error(f"`{name} {' '.join(args)}` failed: '{run_res.stderr}'")
        raise Exception(f"`{name} {args[0]}` failed")
    return run_res.stdout


def kubeconfig_with_server(kubeconfig: dict, server: str) -> dict:
    kubeconfig = copy.deepcopy(kubeconfig)
    for cluster in kubeconfig["clusters"]:
        cluster["cluster"]["server"] = server
    return kubeconfig


class VCluster(NamedTuple):
    """The vCluster standing in for a workload cluster: the runner's client for it, and the
    kubeconfig the management cluster's controllers reach it with."""

    api: pykube.HTTPClient
    kubeconfig: dict


@pytest.fixture(scope="module")
def optional_vcluster(
    kube_cluster: Cluster, kube_config: str, init_namespaces: Any
) -> Iterable[VCluster | None]:
    """A vCluster in the test cluster, standing in for the workload cluster of the out-of-band
    examples, or None when the repository doesn't have the example, so the setup goes on without it.

    `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload
    cluster, and the cluster's HelmReleases install their apps there, through the kubeconfig
    Secret a management cluster has for it. Once the organisation's namespace exists,
    `workload_cluster_objects` creates that Secret in the test cluster with the vCluster's
    kubeconfig, so Flux reconciles the example for real, and what the apps need from the
    management cluster, the cluster values. This fixture creates in the vCluster the CRDs they
    need. kustomize-controller and helm-controller reach the vCluster API server through its
    Service; the runner reaches it on the Service's node port.
    """
    reason = kind_test_config().example_skip_reason(WORKLOAD_CLUSTER_EXAMPLE)
    if reason:
        logger.info(f"No vCluster: {reason}")
        yield None
        return
    node = next(iter(pykube.Node.objects(kube_cluster.kube_client)))
    node_ip = next(
        a["address"]
        for a in node.obj["status"]["addresses"]
        if a["type"] == "InternalIP"
    )
    service_host = (
        f"{WORKLOAD_CLUSTER_VCLUSTER_NAME}.{WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE}.svc"
    )
    values = {
        "controlPlane": {
            "distro": {
                "k8s": {
                    "enabled": True,
                    "image": {"tag": VCLUSTER_KUBERNETES_IMAGE_TAG},
                }
            },
            "statefulSet": {
                "image": {"repository": "loft-sh/vcluster-oss"},
                "persistence": {"volumeClaim": {"enabled": False}},
                # 50m CPU instead of the chart's 200m: the vCluster's apps run on the one kind
                #  node next to it, see node_room.py. It can still use up to its limits.
                "resources": {"requests": {"cpu": "50m"}},
            },
            # CoreDNS stays on, the chart's default: the H3a releases run pods in the vCluster.
            #  Without it, gateway-api-crds and the hello-world of hello-world-from-template
            #  didn't get Ready.
            "proxy": {"extraSANs": [service_host, node_ip]},
            "service": {"spec": {"type": "NodePort"}},
        },
    }
    values_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="vcluster-values-", delete=False
    )
    with values_file:
        yaml.safe_dump(values, values_file)
    try:
        run_tool(
            "helm",
            HELM_URL,
            "upgrade",
            "--install",
            WORKLOAD_CLUSTER_VCLUSTER_NAME,
            "vcluster",
            "--repo",
            VCLUSTER_CHART_REPO,
            "--version",
            VCLUSTER_CHART_VERSION,
            "--namespace",
            WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE,
            "--create-namespace",
            "--values",
            values_file.name,
            "--wait",
            "--timeout",
            f"{VCLUSTER_READY_TIMEOUT_SEC}s",
            "--kubeconfig",
            kube_config,
        )

        # vCluster writes its kubeconfig (server https://localhost:8443) into `vc-<name>`
        vc_secret = vcluster_kubeconfig_secret(
            kube_cluster.kube_client, VCLUSTER_READY_TIMEOUT_SEC
        )
        vc_kubeconfig = yaml.safe_load(
            base64.b64decode(vc_secret.obj["data"]["config"]).decode()
        )
        service = (
            pykube.Service.objects(kube_cluster.kube_client)
            .filter(namespace=WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE)
            .get(name=WORKLOAD_CLUSTER_VCLUSTER_NAME)
        )
        https_port = next(
            p for p in service.obj["spec"]["ports"] if p["name"] == "https"
        )
        # the runner reaches the vCluster on the node port, at the kind node's address
        vcluster_api = pykube.HTTPClient(
            pykube.KubeConfig(
                kubeconfig_with_server(
                    vc_kubeconfig, f"https://{node_ip}:{https_port['nodePort']}"
                )
            )
        )
        # the node port can refuse connections for a moment after the install
        wait_for_api(vcluster_api, 60)
        install_crds(vcluster_api, WORKLOAD_CLUSTER_CRDS_DIR)
        # the vCluster goes away in the end, and its objects with it
        apply(PriorityClass(vcluster_api, WORKLOAD_CLUSTER_PRIORITY_CLASS))

        yield VCluster(
            vcluster_api,
            kubeconfig_with_server(
                vc_kubeconfig, f"https://{service_host}:{https_port['port']}"
            ),
        )
    finally:
        remove_workload_cluster(kube_config, values_file.name)


class NoVClusterError(RuntimeError):
    """The example is there, but optional_vcluster created no vCluster."""

    def __init__(self) -> None:
        super().__init__("The example is there, but there is no vCluster.")


@pytest.fixture(scope="module")
def vcluster(optional_vcluster: VCluster | None) -> VCluster:
    """The vCluster; a test that needs it is skipped, saying why, without the example."""
    require_example(WORKLOAD_CLUSTER_EXAMPLE)
    if optional_vcluster is None:
        raise NoVClusterError
    return optional_vcluster


@pytest.fixture(scope="module")
def workload_cluster(vcluster: VCluster) -> pykube.HTTPClient:
    """The runner's client for the vCluster that stands in for the workload cluster."""
    return vcluster.api


def vcluster_kubeconfig_secret(
    api: pykube.HTTPClient, timeout_polls: int
) -> pykube.Secret:
    """Wait for the Secret vCluster writes its kubeconfig in, `vc-<name>`, and return it.

    `wait_for_objects_condition` polls `timeout_polls` times, a second apart, so the wait takes
    at least that many seconds plus the time of the API calls.
    """
    name = f"vc-{WORKLOAD_CLUSTER_VCLUSTER_NAME}"
    namespace = WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE
    logger.info(f"Waiting for Secret '{namespace}/{name}'")
    try:
        return wait_for_objects_condition(
            api,
            pykube.Secret,
            [name],
            namespace,
            lambda _: True,
            timeout_polls,
            missing_ok=True,
        )[0]
    except TimeoutError as e:
        raise TimeoutError(
            f"Secret '{namespace}/{name}' didn't show up in {timeout_polls} polls."
        ) from e


def remove_workload_cluster(kube_config: str, values_file: str) -> None:
    """Undo the `vcluster` fixture: uninstall the vCluster and remove its values file."""
    try:
        run_tool(
            "helm",
            HELM_URL,
            "uninstall",
            WORKLOAD_CLUSTER_VCLUSTER_NAME,
            # the install may have failed before the release existed; keep its error the one shown
            "--ignore-not-found",
            "--namespace",
            WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE,
            "--wait",
            "--kubeconfig",
            kube_config,
        )
    finally:
        # the uninstall can fail, for example on a `--wait` timeout
        os.remove(values_file)


def wait_for_api(api: pykube.HTTPClient, timeout_sec: int) -> None:
    """Wait until the API server answers `/version`."""
    deadline = time.monotonic() + timeout_sec
    while True:
        try:
            api.get(version="", base="/version").raise_for_status()
            return
        except requests.exceptions.RequestException as e:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"The API server didn't answer in {timeout_sec} s: {e}"
                ) from e
        time.sleep(2)


def apply(obj: pykube.objects.APIObject) -> pykube.objects.APIObject:
    """Create `obj`, or update it if it exists: an interrupted earlier run can leave it behind."""
    if obj.exists():
        obj.update()
    else:
        obj.create()
    return obj


def install_crds(api: pykube.HTTPClient, directory: str) -> None:
    """Create the CustomResourceDefinitions in the `.yaml` files in `directory`, and wait until
    they're served."""
    started = time.monotonic()
    names = []
    for file in sorted(os.listdir(directory)):
        if not file.endswith(".yaml"):
            continue
        with open(os.path.join(directory, file)) as f:
            for doc in yaml.safe_load_all(f):
                if doc and doc.get("kind") == "CustomResourceDefinition":
                    names.append(apply(pykube.CustomResourceDefinition(api, doc)).name)
    if not names:
        raise Exception(f"No CRDs found in '{directory}'")
    deadline = time.monotonic() + 60
    for name in names:
        while True:
            crd = pykube.CustomResourceDefinition.objects(api).get(name=name)
            conditions = crd.obj.get("status", {}).get("conditions") or []
            if any(
                c["type"] == "Established" and c["status"] == "True" for c in conditions
            ):
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"CRD '{name}' isn't established.")
            time.sleep(1)
    logger.info(
        f"Installed {len(names)} CRDs in {time.monotonic() - started:.1f} s: {names}"
    )


@pytest.fixture(scope="module")
def gitops_environment(
    gs_crds: None,
    capi_crds: None,
    init_namespaces: Any,
    gpg_master_key: list[Secret],
    external_secrets: None,
    optional_vcluster: VCluster | None,
    flux_app_deployment: None,
    flux_deployments: list[pykube.Deployment],
    automation_rbac: None,
    organization_objects: list[pykube.objects.APIObject],
) -> None:
    return None


@pytest.fixture(scope="module")
def gitops_root(
    kube_cluster: Cluster,
    gitops_environment: None,
    no_organization_before_bootstrap: None,
    git_repository_factory: GitRepositoryFactoryFunc,
    gitops_test_config: GitOpsTestConfig,
) -> Iterable[Any]:
    """Apply the root Kustomization of every management cluster the test applies, with the
    GitRepositories they read, pointed at the branch under test. With the workflow's token, the
    GitRepositories read the repository with it, so a private one works too."""
    config = kind_test_config()
    for ref in config.git_repositories():
        secret_name = None
        if gitops_test_config.github_token:
            secret = pykube.Secret(
                kube_cluster.kube_client,
                credentials_secret(ref, gitops_test_config.github_token),
            )
            if not secret.exists():
                secret.create()
            secret_name = credentials_secret_name(ref[1])
        git_repository_factory(
            ref[1],
            ref[0],
            "60s",
            gitops_test_config.gitops_repo_url,
            gitops_test_config.gitops_repo_branch,
            secret_ref_name=secret_name,
        )
    applied_manifests: list[str] = []
    for root in config.roots():
        manifest_path = os.path.join(GITOPS_REPO_DIR, root.file)
        logger.info(f"Applying {root.file}, {root.namespace}/{root.name}")
        kube_cluster.kubectl(f"apply -f {manifest_path} --wait=true")
        applied_manifests.append(manifest_path)

    yield None

    for manifest_path in applied_manifests:
        delete_without_prune(kube_cluster, manifest_path)
