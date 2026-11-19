"""Flux's CRDs in the test's workload cluster, for an application team whose Flux runs there.

In the second mode of docs/guides/app-teams.md, Flux runs in the workload cluster, and Flux on
the management cluster delivers the team's GitRepository and Kustomization there. A workload
cluster that runs Flux has its CRDs. The test's vCluster runs no Flux: the team's objects only
have to exist there, so the fixture copies just the CRDs of their kinds from the test cluster,
where flux-app installed them, at the version GITOPS_FLUX_APP_VERSION names.
"""

import tempfile
from pathlib import Path

import pykube
import pytest
import yaml
from conftest import install_crds
from pytest_helm_charts.clusters import Cluster

# the kinds of the team's objects: its GitRepository and its Kustomization
FLUX_CRDS = [
    "gitrepositories.source.toolkit.fluxcd.io",
    "kustomizations.kustomize.toolkit.fluxcd.io",
]


def crd_copy(crd: dict) -> dict:
    """The CRD `crd`, without what its cluster set, so it can be created in another one."""
    return {
        "apiVersion": crd["apiVersion"],
        "kind": crd["kind"],
        "metadata": {"name": crd["metadata"]["name"]},
        "spec": crd["spec"],
    }


@pytest.fixture(scope="module")
def workload_cluster_flux_crds(
    kube_cluster: Cluster,
    flux_app_deployment: None,
    workload_cluster: pykube.HTTPClient,
) -> None:
    crds = pykube.CustomResourceDefinition.objects(kube_cluster.kube_client)
    with tempfile.TemporaryDirectory(prefix="flux-crds-") as directory:
        for name in FLUX_CRDS:
            with (Path(directory) / f"{name}.yaml").open("w") as f:
                yaml.safe_dump(crd_copy(crds.get(name=name).obj), f)
        install_crds(workload_cluster, directory)
