import base64
import copy
import logging
import os
import shutil
import subprocess  # nosec B404 - we need to invoke processes
import tempfile
import time
from typing import Iterable, Any

import pykube
import pytest
import validators
import yaml
from pykube import Secret
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.git_repository import GitRepositoryFactoryFunc
from pytest_helm_charts.giantswarm_app_platform.app import AppFactoryFunc, ConfiguredApp

FLUX_GIT_REPO_NAME = "your-repo"

FLUX_OBJECTS_NAMESPACE = "default"
FLUX_SOPS_MASTER_KEY_SECRET_NAME = "sops-gpg-master"  # nosec B105 - not a secret here
FLUX_IMPERSONATION_SA_NAME = "automation"

CLUSTER_CTL_PROVIDERS_MAP = {"aws": "v1.2.0", "azure": "v1.0.1"}

# Every provider is pinned to an explicit release URL, including the ones
# `clusterctl init` installs implicitly (the core provider and the kubeadm
# bootstrap/control-plane pair).
#
# The stock URLs end in `/releases/latest/`, and clusterctl takes the version
# straight out of that path when it builds the repository client -- before it
# ever looks at what `--core`/`--infrastructure` asked for. Resolving "latest"
# means: read the newest cluster-api release's metadata.yaml, find the release
# series serving the v1beta1 contract this clusterctl speaks (1.10), then search
# for a 1.10.x tag. That search only covers the 30 newest releases, because
# clusterctl requests the release list with no paging options. cluster-api
# published its 30th release since v1.10.10 on 2026-08-11, so 1.10.x dropped out
# of the window and the lookup has returned nothing since, reported as the
# misleading "failed to find releases tagged with a valid semantic version
# number". A pinned URL skips the resolution entirely.
#
# v1.10.10 is the newest release of the 1.10 series, which is what the "latest"
# resolution above was picking until 2026-08-11 -- GetReleaseSeriesForContract
# returns the newest series serving v1beta1, and 1.10 is it. Pinning it keeps
# this suite on the CAPI version it was already exercising, rather than dropping
# back to the vintage of the clusterctl binary itself. Going past the v1beta1
# contract needs a newer clusterctl (the workflow pins 1.2.0) and new enough
# infrastructure providers, which is a bigger change than this fix.
CLUSTER_CTL_CORE_VERSION = "v1.10.10"
CLUSTER_CTL_RELEASE_URL = (
    "https://github.com/kubernetes-sigs/{repo}/releases/{version}/{components}"
)
CLUSTER_CTL_PROVIDER_REPOS = {
    "aws": "cluster-api-provider-aws",
    "azure": "cluster-api-provider-azure",
}

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT_SEC = 180
CLUSTER_CTL_URL = "https://github.com/kubernetes-sigs/cluster-api/releases/"
APPTESTCTL_URL = "https://github.com/giantswarm/apptestctl/releases"
GS_CRDS_URLS = [
    "https://raw.githubusercontent.com/giantswarm/apiextensions/master/helm/crds-common/templates/"
    + "security.giantswarm.io_organizations.yaml"
]
GITOPS_TOP_DIR = "../../management-clusters"

HELM_URL = "https://helm.sh/docs/intro/install/"
# A vCluster inside the test cluster stands in for the workload cluster the -direct out-of-band
# example targets. The Secret is the one its Kustomization reads through `spec.kubeConfig.secretRef`.
WORKLOAD_CLUSTER_VCLUSTER_NAME = "mapi-out-of-band-no-flux"
WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE = "vcluster-mapi-out-of-band-no-flux"
VCLUSTER_CHART_REPO = "https://charts.loft.sh"
VCLUSTER_CHART_VERSION = "0.37.6"
VCLUSTER_READY_TIMEOUT_SEC = 300
WORKLOAD_CLUSTER_KUBECONFIG_NAME = "mapi-out-of-band-no-flux-kubeconfig"
WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE = "org-org-name"

logger = logging.getLogger(__name__)

# Experiment instrumentation: how long each fixture's setup and teardown took, printed at the
#  end of the run.
FIXTURE_SECONDS: list[tuple[str, str, float]] = []


@pytest.hookimpl(wrapper=True)
def pytest_fixture_setup(fixturedef: Any, request: Any) -> Any:
    teardown_start: list[float] = []
    # finalizers run last in, first out: this one runs after the fixture's own teardown ...
    fixturedef.addfinalizer(
        lambda: (
            FIXTURE_SECONDS.append(
                ("teardown", fixturedef.argname, time.monotonic() - teardown_start[0])
            )
            if teardown_start
            else None
        )
    )
    start = time.monotonic()
    try:
        return (yield)
    finally:
        FIXTURE_SECONDS.append(("setup", fixturedef.argname, time.monotonic() - start))
        # ... and this one before it
        fixturedef.addfinalizer(lambda: teardown_start.append(time.monotonic()))


def pytest_terminal_summary(terminalreporter: Any) -> None:
    terminalreporter.write_sep("-", "fixture durations")
    for phase, name, seconds in FIXTURE_SECONDS:
        terminalreporter.write_line(f"{seconds:9.2f}s {phase:8} {name}")


class GitOpsTestConfig:
    _GITOPS_REPO_URL_ENV_VAR_NAME = "GITOPS_REPO_URL"
    _GITOPS_REPO_BRANCH_ENV_VAR_NAME = "GITOPS_REPO_BRANCH"
    _FLUX_INIT_NAMESPACES_ENV_VAR_NAME = "GITOPS_INIT_NAMESPACES"
    _GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME = "GITOPS_MASTER_GPG_KEY"
    _FLUX_APP_VERSION = "GITOPS_FLUX_APP_VERSION"
    _IGNORED_OBJECTS = "GITOPS_IGNORED_OBJECTS"

    def __init__(self) -> None:
        env_var_namespaces = os.getenv(self._FLUX_INIT_NAMESPACES_ENV_VAR_NAME)
        if env_var_namespaces:
            namespaces = env_var_namespaces.split(",")
        else:
            namespaces = ["default"]
        self.init_namespaces = namespaces

        self.master_private_key = os.environ[self._GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME]
        if not self.master_private_key:
            logger.error(
                f"In order to bootstrap the repository, armor-encoded master private GPG key for the gitops"
                f" repo has to be set in '{self._GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' environment variable"
                f" (base64 encoded)."
            )
            raise Exception("master gpg key missing")

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
        ignored_objects = os.environ.get(self._IGNORED_OBJECTS, "")
        self.ignored_objects: list[str] = [
            o for o in ignored_objects.split(",") if o.strip()
        ]


@pytest.fixture(scope="module")
def gitops_test_config() -> GitOpsTestConfig:
    return GitOpsTestConfig()


@pytest.fixture(scope="module")
def flux_app_deployment(
    kube_cluster: Cluster,
    app_factory: AppFactoryFunc,
    gitops_test_config: GitOpsTestConfig,
) -> ConfiguredApp:
    logger.debug(
        f"Deploying 'flux-app' in version '{gitops_test_config.flux_app_version}'."
    )
    return app_factory(
        "flux-app",
        gitops_test_config.flux_app_version,
        "giantswarm",
        FLUX_OBJECTS_NAMESPACE,
        "https://giantswarm.github.io/giantswarm-catalog/",
    )


@pytest.fixture(scope="module")
def gs_crds(kube_cluster: Cluster) -> None:
    logger.debug("Deploying Giant Swarm CRDs to the test cluster")
    for crd in GS_CRDS_URLS:
        kube_cluster.kubectl(f"apply -f {crd}")


def write_clusterctl_config() -> str:
    """Write a clusterctl config pinning every provider to an explicit release URL.

    Returns the path of the generated file. See CLUSTER_CTL_CORE_VERSION for why
    the stock "latest" URLs cannot be used any more.
    """
    core = [
        ("cluster-api", "CoreProvider", "core-components.yaml"),
        ("kubeadm", "BootstrapProvider", "bootstrap-components.yaml"),
        ("kubeadm", "ControlPlaneProvider", "control-plane-components.yaml"),
    ]
    providers = [
        {
            "name": name,
            "type": provider_type,
            "url": CLUSTER_CTL_RELEASE_URL.format(
                repo="cluster-api",
                version=CLUSTER_CTL_CORE_VERSION,
                components=components,
            ),
        }
        for name, provider_type, components in core
    ]
    providers += [
        {
            "name": name,
            "type": "InfrastructureProvider",
            "url": CLUSTER_CTL_RELEASE_URL.format(
                repo=CLUSTER_CTL_PROVIDER_REPOS[name],
                version=version,
                components="infrastructure-components.yaml",
            ),
        }
        for name, version in CLUSTER_CTL_PROVIDERS_MAP.items()
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", prefix="clusterctl-", delete=False
    ) as config_file:
        yaml.safe_dump({"providers": providers}, config_file)
        return config_file.name


@pytest.fixture(scope="module")
def capi_controllers(kube_config: str) -> Iterable[Any]:
    cluster_ctl_path = shutil.which("clusterctl")

    if not cluster_ctl_path:
        logger.error(
            f"You must install `clusterctl` tool from '{CLUSTER_CTL_URL}' and make it available "
            f"in your $PATH."
        )
        raise Exception("`clusterctl` not found")

    logger.debug(f"Using '{cluster_ctl_path}' to bootstrap CAPI controllers")
    clusterctl_config = write_clusterctl_config()
    infra_providers = ",".join(":".join(p) for p in CLUSTER_CTL_PROVIDERS_MAP.items())
    fake_secret = base64.b64encode(b"something")
    env_vars = os.environ | {
        "AWS_B64ENCODED_CREDENTIALS": fake_secret,
        "AZURE_SUBSCRIPTION_ID_B64": fake_secret,
        "AZURE_TENANT_ID_B64": fake_secret,
        "AZURE_CLIENT_ID_B64": fake_secret,
        "AZURE_CLIENT_SECRET_B64": fake_secret,
        "EXP_MACHINE_POOL": "true",
    }
    try:
        run_res = subprocess.run(  # nosec B603 - no user provided config except of kube.config path
            [
                cluster_ctl_path,
                "init",
                "--kubeconfig",
                kube_config,
                f"--infrastructure={infra_providers}",
                "--config",
                clusterctl_config,
            ],
            capture_output=True,
            env=env_vars,  # type: ignore # for some reason mypy thinks the type here is 'Dict[str, Sequence[object]]'
        )
    finally:
        # Only `init` reads the provider URLs; `delete` works from the cluster's inventory.
        os.remove(clusterctl_config)
    if run_res.returncode != 0:
        logger.error(
            f"Error bootstrapping CAPI on test cluster: '{run_res.stderr}'"  # type: ignore
        )
        raise Exception("Cannot bootstrap CAPI")

    yield None

    run_res = subprocess.run(  # nosec B603 - no user provided config except of kube.config path
        [cluster_ctl_path, "delete", "--kubeconfig", kube_config, "--all"],
        capture_output=True,
        env=env_vars,  # type: ignore # for some reason mypy thinks the type here is 'Dict[str, Sequence[object]]'
    )
    if run_res.returncode != 0:
        logger.error(
            f"Error cleaning up CAPI on test cluster: '{run_res.stderr}'"  # type: ignore
        )
        raise Exception("Cannot clean up CAPI")


@pytest.fixture(scope="module")
def app_platform_controllers(kube_config: str) -> None:
    apptestctl_path = shutil.which("apptestctl")

    if not apptestctl_path:
        logger.error(
            f"You must install `apptestctl` tool from '{APPTESTCTL_URL}' and make it available "
            f"in your $PATH."
        )
        raise Exception("`apptestctl` not found")

    logger.debug(f"Using '{apptestctl_path}' to bootstrap app platform controllers")
    run_res = subprocess.run(  # nosec B603 - no user provided config except of kube.config path
        [
            apptestctl_path,
            "bootstrap",
            "--kubeconfig-path",
            kube_config,
        ],
        capture_output=True,
    )
    if run_res.returncode != 0:
        logger.error(
            f"Error bootstrapping app platform on test cluster: '{run_res.stderr}'"  # type: ignore
        )
        raise Exception("Cannot bootstrap app platform")


@pytest.fixture(scope="module")
def init_namespaces(
    kube_cluster: Cluster, gitops_test_config: GitOpsTestConfig
) -> Iterable[Any]:
    created_namespaces: list[pykube.Namespace] = []
    created_cluster_role_bindings: list[pykube.ClusterRoleBinding] = []
    created_service_accounts: list[pykube.ServiceAccount] = []

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

        sa_on_cluster = (
            pykube.ServiceAccount.objects(kube_cluster.kube_client)
            .filter(namespace=ns)
            .get_or_none(name=FLUX_IMPERSONATION_SA_NAME)
        )
        if not sa_on_cluster:
            sa = pykube.ServiceAccount(
                kube_cluster.kube_client,
                {"metadata": {"name": FLUX_IMPERSONATION_SA_NAME, "namespace": ns}},
            )
            sa.create()
            created_service_accounts.append(sa)

        crb_name = f"{FLUX_IMPERSONATION_SA_NAME}-cluster-admin-{ns}"
        crb_on_cluster = pykube.ClusterRoleBinding.objects(
            kube_cluster.kube_client
        ).get_or_none(name=crb_name)
        if not crb_on_cluster:
            crb = pykube.ClusterRoleBinding(
                kube_cluster.kube_client,
                {
                    "metadata": {
                        "name": crb_name,
                    },
                    "roleRef": {"kind": "ClusterRole", "name": "cluster-admin"},
                    "subjects": [
                        {
                            "kind": "ServiceAccount",
                            "name": FLUX_IMPERSONATION_SA_NAME,
                            "namespace": ns,
                        }
                    ],
                },
            )
            crb.create()
            created_cluster_role_bindings.append(crb)

    yield

    for sa in created_service_accounts:
        sa.delete()
    for namespace in created_namespaces:
        namespace.delete()
    for crb in created_cluster_role_bindings:
        crb.delete()


@pytest.fixture(scope="module")
def gpg_master_key(
    kube_cluster: Cluster, gitops_test_config: GitOpsTestConfig
) -> Iterable[Secret]:
    # create the master gpg secret used to unlock all encrypted values
    gpg_master_key = pykube.Secret(
        kube_cluster.kube_client,
        {
            "metadata": {
                "name": FLUX_SOPS_MASTER_KEY_SECRET_NAME,
                "namespace": FLUX_OBJECTS_NAMESPACE,
            },
            "type": "Opaque",
            "data": {
                "mc-name.master.asc": gitops_test_config.master_private_key,
            },
        },
    )
    gpg_master_key.create()

    yield gpg_master_key

    gpg_master_key.delete()


def run_helm(*args: str) -> str:
    helm_path = shutil.which("helm")
    if not helm_path:
        logger.error(
            f"You must install `helm` from '{HELM_URL}' and make it available in your $PATH."
        )
        raise Exception("`helm` not found")
    run_res = subprocess.run(  # nosec B603 - fixed arguments, no user input
        [helm_path, *args], capture_output=True, text=True
    )
    if run_res.returncode != 0:
        logger.error(f"`helm {' '.join(args)}` failed: '{run_res.stderr}'")
        raise Exception(f"`helm {args[0]}` failed")
    return run_res.stdout


def kubeconfig_with_server(kubeconfig: dict, server: str) -> dict:
    kubeconfig = copy.deepcopy(kubeconfig)
    for cluster in kubeconfig["clusters"]:
        cluster["cluster"]["server"] = server
    return kubeconfig


@pytest.fixture(scope="module")
def workload_cluster(
    kube_cluster: Cluster, kube_config: str, init_namespaces: Any
) -> Iterable[pykube.HTTPClient]:
    """A vCluster in the test cluster, standing in for the workload cluster of the -direct example.

    `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload
    cluster through the kubeconfig Secret a management cluster has for it. The fixture creates
    that Secret in the test cluster with the vCluster's kubeconfig, so Flux reconciles the
    example for real. kustomize-controller reaches the vCluster API server through its Service;
    the runner reaches it on the Service's node port.
    """
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
            "distro": {"k8s": {"enabled": True}},
            "statefulSet": {
                "image": {"repository": "loft-sh/vcluster-oss"},
                "persistence": {"volumeClaim": {"enabled": False}},
            },
            # nothing in the test runs pods in the vCluster
            "coredns": {"enabled": False},
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
        run_helm(
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
        vc_secret = wait_for_secret(
            kube_cluster.kube_client,
            f"vc-{WORKLOAD_CLUSTER_VCLUSTER_NAME}",
            WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE,
        )
        vc_kubeconfig = yaml.safe_load(
            base64.b64decode(vc_secret.obj["data"]["config"]).decode()
        )
        service = pykube.Service.objects(kube_cluster.kube_client).get(
            name=WORKLOAD_CLUSTER_VCLUSTER_NAME,
            namespace=WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE,
        )
        https_port = next(
            p for p in service.obj["spec"]["ports"] if p["name"] == "https"
        )

        kubeconfig_secret = pykube.Secret(
            kube_cluster.kube_client,
            {
                "metadata": {
                    "name": WORKLOAD_CLUSTER_KUBECONFIG_NAME,
                    "namespace": WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE,
                },
                "type": "Opaque",
                "stringData": {
                    "value": yaml.safe_dump(
                        kubeconfig_with_server(
                            vc_kubeconfig,
                            f"https://{service_host}:{https_port['port']}",
                        )
                    )
                },
            },
        )
        kubeconfig_secret.create()

        # the runner reaches the vCluster on the node port, at the kind node's address
        yield pykube.HTTPClient(
            pykube.KubeConfig(
                kubeconfig_with_server(
                    vc_kubeconfig, f"https://{node_ip}:{https_port['nodePort']}"
                )
            )
        )

        kubeconfig_secret.delete()
    finally:
        run_helm(
            "uninstall",
            WORKLOAD_CLUSTER_VCLUSTER_NAME,
            "--namespace",
            WORKLOAD_CLUSTER_VCLUSTER_NAMESPACE,
            "--wait",
            "--kubeconfig",
            kube_config,
        )
        os.remove(values_file.name)


def wait_for_secret(api: pykube.HTTPClient, name: str, namespace: str) -> pykube.Secret:
    deadline = time.monotonic() + VCLUSTER_READY_TIMEOUT_SEC
    while True:
        secret = (
            pykube.Secret.objects(api)
            .filter(namespace=namespace)
            .get_or_none(name=name)
        )
        if secret is not None:
            return secret
        if time.monotonic() > deadline:
            raise TimeoutError(f"Secret '{namespace}/{name}' didn't show up.")
        time.sleep(2)


@pytest.fixture(scope="module")
def gitops_environment(
    gs_crds: None,
    capi_controllers: None,
    app_platform_controllers: None,
    init_namespaces: Any,
    gpg_master_key: Secret,
    workload_cluster: pykube.HTTPClient,
    flux_app_deployment: ConfiguredApp,
    flux_deployments: list[pykube.Deployment],
) -> ConfiguredApp:
    return flux_app_deployment


@pytest.fixture(scope="module")
def gitops_deployment(
    kube_cluster: Cluster,
    gitops_environment: ConfiguredApp,
    git_repository_factory: GitRepositoryFactoryFunc,
    gitops_test_config: GitOpsTestConfig,
) -> Iterable[Any]:
    git_repository_factory(
        FLUX_GIT_REPO_NAME,
        FLUX_OBJECTS_NAMESPACE,
        "60s",
        gitops_test_config.gitops_repo_url,
        gitops_test_config.gitops_repo_branch,
    )
    applied_manifests: list[str] = []
    for dir_entry in os.scandir(GITOPS_TOP_DIR):
        if dir_entry.is_dir():
            manifest_path = os.path.join(
                GITOPS_TOP_DIR, dir_entry.name, dir_entry.name + ".yaml"
            )
            kube_cluster.kubectl(f"apply -f {manifest_path} --wait=true")
            applied_manifests.append(manifest_path)

    yield None

    for manifest_path in applied_manifests:
        kube_cluster.kubectl(
            f"delete -f {manifest_path} --wait=true", output_format="text"
        )
