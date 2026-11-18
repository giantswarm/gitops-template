"""Deleting what the kind test applied without Flux deleting what the Kustomizations applied."""

import pykube
from pykube.exceptions import HTTPError
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.kustomization import KustomizationCR


def delete_without_prune(kube_cluster: Cluster, manifest_path: str) -> None:
    """Delete the Kustomizations in `manifest_path`, and nothing they applied.

    The Kustomizations have `prune: true`. Deleting one would delete what it applied, and the
    cluster Kustomizations would delete their apps, while the vCluster and the namespaces go
    at the same time. Every Kustomization is suspended with `prune: false` first, so the
    deletion takes nothing with it, and what the other fixtures delete next goes in their order.
    """
    for k in KustomizationCR.objects(kube_cluster.kube_client).filter(
        namespace=pykube.all
    ):
        try:
            k.patch({"spec": {"suspend": True, "prune": False}})
        except HTTPError as e:
            # deleted since it was listed, such as the cluster Kustomization test_prune deletes
            if e.code != 404:
                raise
    kube_cluster.kubectl(f"delete -f {manifest_path} --wait=true", output_format="text")
