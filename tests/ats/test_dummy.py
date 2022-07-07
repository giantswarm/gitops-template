import base64
import logging
import os
import platform
import shutil
import subprocess
import stat
import tempfile
import validators
from typing import Callable, Iterable, Any

import pykube
import pytest
import requests
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.git_repository import GitRepositoryFactoryFunc
from pytest_helm_charts.flux.kustomization import KustomizationFactoryFunc
from pytest_helm_charts.giantswarm_app_platform.app import AppFactoryFunc, ConfiguredApp
from pytest_helm_charts.k8s.deployment import wait_for_deployments_to_run

FLUX_GIT_REPO_NAME = "your-repo"

FLUX_OBJECTS_NAMESPACE = "default"
FLUX_SOPS_MASTER_KEY_SECRET_NAME = "sops-gpg-master"
FLUX_IMPERSONATION_SA_NAME = "automation"


FLUX_VERSION = "0.11.0"
CLUSTER_CTL_VERSION = "1.1.4"
CLUSTER_CTL_PROVIDERS_MAP = {"aws": "v1.2.0", "azure": "v1.0.1"}

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT: int = 180
CLUSTER_CTL_URL = f"https://github.com/kubernetes-sigs/cluster-api/releases/download/v{CLUSTER_CTL_VERSION}/clusterctl-"
GS_CRDS_COMMIT_URL = "https://raw.githubusercontent.com/giantswarm/apiextensions/15836a106059cc8d201e1237adf44aec340bbab6/helm/crds-common/templates/giantswarm.yaml"

logger = logging.getLogger(__name__)


class GitOpsTestConfig:
    _GITOPS_REPO_URL_ENV_VAR_NAME = "GITOPS_REPO_URL"
    _GITOPS_REPO_BRANCH_ENV_VAR_NAME = "GITOPS_REPO_BRANCH"
    _FLUX_INIT_NAMESPACES_ENV_VAR_NAME = "GITOPS_INIT_NAMESPACES"
    _GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME = "GITOPS_MASTER_GPG_KEY"

    def __init__(self):
        env_var_namespaces = os.getenv(self._FLUX_INIT_NAMESPACES_ENV_VAR_NAME)
        if env_var_namespaces:
            namespaces = env_var_namespaces.split(",")
        else:
            namespaces = ["default"]
        self.init_namespaces = namespaces

        self.master_private_key = os.environ[self._GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME]
        if not self.master_private_key:
            logger.error(f"In order to bootstrap the repository, armor-encoded master private GPG key for the gitops"
                         f" repo has to be set in '{self._GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' environment variable"
                         f" (base64 encoded).")
            raise Exception("master gpg key missing")

        self.gitops_repo_url = os.environ[self._GITOPS_REPO_URL_ENV_VAR_NAME]
        if not validators.url(self.gitops_repo_url):
            logger.error(f"The '{self._GITOPS_REPO_URL_ENV_VAR_NAME}' environment variable must point to the gitops "
                         f"repository you want to run tests for (malformed URL)"
                         f" [current value: '{self.gitops_repo_url}'].")
            raise Exception("malformed gitops repo URL")

        self.gitops_repo_branch = os.environ[self._GITOPS_REPO_BRANCH_ENV_VAR_NAME]
        if not self.gitops_repo_branch:
            logger.error(f"The '{self._GITOPS_REPO_BRANCH_ENV_VAR_NAME}' environment variable must point to a branch "
                         f"in the gitops repository configured by '{self.gitops_repo_url}'"
                         f" [current value: '{self.gitops_repo_branch}'].")
            raise Exception("gitops repo branch name missing")


@pytest.fixture(scope="module")
def gitops_test_config() -> GitOpsTestConfig:
    return GitOpsTestConfig()


@pytest.fixture(scope="module")
def flux_app_deployment(kube_cluster: Cluster, app_factory: AppFactoryFunc) -> ConfiguredApp:
    return app_factory("flux-app", FLUX_VERSION, "giantswarm", FLUX_OBJECTS_NAMESPACE,
                       "https://giantswarm.github.io/giantswarm-catalog/")


# @pytest.fixture(scope="module")
# def gs_crds(kube_cluster: Cluster) -> None:
#    logger.debug("Deploying Giant Swarm CRDs to the test cluster")
#    kube_cluster.kubectl(f"apply -f {GS_CRDS_COMMIT_URL}")
#
#
# @pytest.fixture(scope="module")
# def capi_controllers(kube_config: str) -> Iterable[Any]:
#    cluster_ctl_path = shutil.which("clusterctl")
#
#    if not cluster_ctl_path:
#        cluster_ctl_path = os.path.join(tempfile.gettempdir(), "clusterctl")
#
#        if not os.access(cluster_ctl_path, os.X_OK):
#            logger.debug("Cannot find existing 'clusterctl' binary, attempting to download")
#            uname_info = platform.uname()
#            sys_type = uname_info.system.lower()
#            arch_type = "arm64" if uname_info.machine == "arm64" else "amd64"
#            url = f"{CLUSTER_CTL_URL}-{sys_type}-{arch_type}"
#            r = requests.get(url, allow_redirects=True)
#            if not r.ok:
#                logger.error(f"Can't download 'clusterctl': [{r.status_code}] {r.reason}")
#                raise Exception("error downloading `clusterctl`")
#            open(cluster_ctl_path, 'wb').write(r.content)
#            st = os.stat(cluster_ctl_path)
#            os.chmod(cluster_ctl_path, st.st_mode | stat.S_IEXEC)
#
#    logger.debug(f"Using '{cluster_ctl_path}' to bootstrap CAPI controllers")
#    infra_providers = ",".join(":".join(p) for p in CLUSTER_CTL_PROVIDERS_MAP.items())
#    fake_secret = base64.b64encode(b'something')
#    env_vars = os.environ | {
#        "AWS_B64ENCODED_CREDENTIALS": fake_secret,
#        "AZURE_SUBSCRIPTION_ID_B64": fake_secret,
#        "AZURE_TENANT_ID_B64": fake_secret,
#        "AZURE_CLIENT_ID_B64": fake_secret,
#        "AZURE_CLIENT_SECRET_B64": fake_secret,
#        "EXP_MACHINE_POOL": "true"}
#    run_res = subprocess.run(
#        [cluster_ctl_path, "init", "--kubeconfig", kube_config, f"--infrastructure={infra_providers}"],
#        capture_output=True, env=env_vars)
#    if run_res.returncode != 0:
#        logger.error(f"Error bootstrapping CAPI on test cluster failed: '{run_res.stderr}'")
#        raise Exception(f"Cannot bootstrap CAPI")
#    yield None
#    run_res = subprocess.run(
#        [cluster_ctl_path, "delete", "--kubeconfig", kube_config, "--all"],
#        capture_output=True, env=env_vars)
#    if run_res.returncode != 0:
#        logger.error(f"Error cleaning up CAPI on test cluster failed: '{run_res.stderr}'")
#        raise Exception(f"Cannot clean up CAPI")

@pytest.fixture(scope="module")
def init_namespaces(kube_cluster: Cluster, gitops_test_config: GitOpsTestConfig) -> None:
    created_namespaces = []
    for ns in gitops_test_config.init_namespaces:
        ns_on_cluster = pykube.Namespace.objects(kube_cluster.kube_client).get_or_none(name=ns)
        if not ns_on_cluster:
            new_ns = pykube.Namespace(kube_cluster.kube_client, {"metadata": {"name": ns}})
            new_ns.create()
            created_namespaces.append(new_ns)
        sa_on_cluster = pykube.ServiceAccount.objects(kube_cluster.kube_client).filter(namespace=ns).get_or_none(
            name=FLUX_IMPERSONATION_SA_NAME)
        if not sa_on_cluster:
            pykube.ServiceAccount(kube_cluster.kube_client,
                                  {"metadata": {"name": FLUX_IMPERSONATION_SA_NAME, "namespace": ns}}).create()
            pykube.ClusterRoleBinding(kube_cluster.kube_client, {
                "metadata": {
                    "name": f"{FLUX_IMPERSONATION_SA_NAME}-cluster-admin-{ns}",
                },
                "roleRef": {
                    "kind": "ClusterRole",
                    "name": "cluster-admin"
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": FLUX_IMPERSONATION_SA_NAME,
                        "namespace": ns
                    }
                ]
            }).create()
    yield

    for ns in created_namespaces:
        ns.delete()


@pytest.fixture(scope="module")
def gitops_flux_deployment(kube_cluster: Cluster,
                           git_repository_factory: GitRepositoryFactoryFunc,
                           init_namespaces: Any,
                           gitops_test_config: GitOpsTestConfig) -> Iterable[Any]:
    # create the master gpg secret used to unlock all encrypted values

    gpg_master_key = pykube.Secret(kube_cluster.kube_client, {
        "metadata": {
            "name": FLUX_SOPS_MASTER_KEY_SECRET_NAME,
            "namespace": FLUX_OBJECTS_NAMESPACE,
        },
        "type": "Opaque",
        "data": {
            "mc-name.master.asc": gitops_test_config.master_private_key,
        },
    })
    gpg_master_key.create()
    git_repo = git_repository_factory(FLUX_GIT_REPO_NAME, FLUX_OBJECTS_NAMESPACE, "6s",
                                      gitops_test_config.gitops_repo_url, gitops_test_config.gitops_repo_branch)
    kube_cluster.kubectl("apply -f ../../management-clusters/MC_NAME/MC_NAME.yaml")
    yield None
    gpg_master_key.delete()
    # FIXME: delete doens't return text, so this call fails
    kube_cluster.kubectl("delete -f ../../management-clusters/MC_NAME/MC_NAME.yaml")


@pytest.fixture(scope="module")
def gitops_environment(
        # flux_app_deployment: ConfiguredApp,
        flux_deployments: list[pykube.Deployment],
        # gs_crds: None,
        # capi_controllers: None,
        gitops_flux_deployment: None,
) -> ConfiguredApp:
    # return flux_app_deployment
    return


@pytest.mark.smoke
def test_dummy(gitops_environment) -> None:
    print("good")
    pass
