import base64
import logging
import os
import shutil
import subprocess  # nosec B404 - we need to invoke processes
import tempfile
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
# These pins are what keeps this suite working against a 2022-era CAPI stack.
# Moving to a current clusterctl and current providers is the durable fix, but
# it means moving the example manifests off the v1beta1 contract as well.
CLUSTER_CTL_CORE_VERSION = "v1.2.0"
CLUSTER_CTL_RELEASE_URL = "https://github.com/kubernetes-sigs/{repo}/releases/{version}/{components}"
CLUSTER_CTL_PROVIDER_REPOS = {"aws": "cluster-api-provider-aws", "azure": "cluster-api-provider-azure"}

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT_SEC = 180
CLUSTER_CTL_URL = "https://github.com/kubernetes-sigs/cluster-api/releases/"
APPTESTCTL_URL = "https://github.com/giantswarm/apptestctl/releases"
GS_CRDS_URLS = [
    "https://raw.githubusercontent.com/giantswarm/apiextensions/master/helm/crds-common/templates/"
    + "security.giantswarm.io_organizations.yaml"
]
GITOPS_TOP_DIR = "../../management-clusters"

logger = logging.getLogger(__name__)


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

        ignored_objects = os.environ[self._IGNORED_OBJECTS]
        if ignored_objects:
            self.ignored_objects = ignored_objects.split(",")


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


@pytest.fixture(scope="module")
def gitops_environment(
    gs_crds: None,
    capi_controllers: None,
    app_platform_controllers: None,
    init_namespaces: Any,
    gpg_master_key: Secret,
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
