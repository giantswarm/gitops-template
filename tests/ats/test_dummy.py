import base64
import logging
import os
import platform
import shutil
import subprocess
import stat
import tempfile
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
# TODO: load from env vars
FLUX_GIT_REPO_URL = "https://github.com/giantswarm/gitops-template"
FLUX_GIT_REPO_BRANCH = "tests/deploy-gitops-repo"

FLUX_OBJECTS_NAMESPACE = "default"
FLUX_SOPS_MASTER_KEY_SECRET_NAME = "sops-gpg-master"

GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME = "GITOPS_MASTER_GPG_KEY"

FLUX_VERSION = "0.11.0"
CLUSTER_CTL_VERSION = "1.1.4"
CLUSTER_CTL_PROVIDERS_MAP = {"aws": "v1.2.0", "azure": "v1.0.1"}

FLUX_NAMESPACE_NAME = "default"
FLUX_DEPLOYMENTS_READY_TIMEOUT: int = 180
CLUSTER_CTL_URL = f"https://github.com/kubernetes-sigs/cluster-api/releases/download/v{CLUSTER_CTL_VERSION}/clusterctl-"
GS_CRDS_COMMIT_URL = "https://raw.githubusercontent.com/giantswarm/apiextensions/15836a106059cc8d201e1237adf44aec340bbab6/helm/crds-common/templates/giantswarm.yaml"

logger = logging.getLogger(__name__)


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
def gitops_flux_deployment(git_repository_factory: GitRepositoryFactoryFunc,
                           kube_cluster: Cluster) -> Iterable[Any]:
    # create the master gpg secret used to unlock all encrypted values
    master_private_key = os.environ[GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME]
    if not master_private_key:
        logger.error(f"In order to bootstrap the repository, armor-encoded master private GPG key for the gitops"
                     f" repo has to be set in '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' environment variable"
                     f" (base64 encoded).")
        raise Exception("master gpg key missing")

    gpg_master_key = pykube.Secret(kube_cluster.kube_client, {
        "metadata": {
            "name": FLUX_SOPS_MASTER_KEY_SECRET_NAME,
            "namespace": FLUX_OBJECTS_NAMESPACE,
        },
        "type": "Opaque",
        "data": {
            "test": master_private_key,
        },
    })
    gpg_master_key.create()
    git_repo = git_repository_factory(FLUX_GIT_REPO_NAME, FLUX_OBJECTS_NAMESPACE, "3600s", FLUX_GIT_REPO_URL,
                                      FLUX_GIT_REPO_BRANCH)
    kube_cluster.kubectl("apply -f ../../management-clusters/MC_NAME/MC_NAME.yaml")
    yield None
    kube_cluster.kubectl("delete -f ../../management-clusters/MC_NAME/MC_NAME.yaml")
    gpg_master_key.delete()


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
