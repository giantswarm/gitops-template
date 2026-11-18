"""P3: deleting a cluster's Kustomization deletes what it applied, except the cluster.

When a cluster's Kustomization goes, because its file is deleted from Git or by hand as the
getting-started guides do, Flux deletes everything it applied, except what has
`kustomize.toolkit.fluxcd.io/prune: disabled`: the cluster's HelmRelease stays.
"""

import pykube
from checks.assertion_files import WORKLOAD_CLUSTER_ASSERTIONS_DIR, load_assertions
from checks.conditions import obj_key
from flux_inventory import inventory_keys
from flux_reconcile import suspend, wait_until
from prune_objects import (
    CLUSTER_KUSTOMIZATION,
    PRUNE_TIMEOUT_SEC,
    ROOT_KUSTOMIZATION,
)
from prune_source import kustomization


def delete_cluster_kustomization(api: pykube.HTTPClient) -> set[tuple[str, str, str]]:
    """Delete the cluster's Kustomization and wait until it's gone; return what it applied.

    The management cluster's Kustomization is suspended first, so it doesn't create it again.
    """
    suspend(kustomization(api, ROOT_KUSTOMIZATION))
    cluster = kustomization(api, CLUSTER_KUSTOMIZATION)
    applied = inventory_keys(cluster.obj)
    cluster.delete()
    wait_until(
        lambda: (
            [f"Kustomization '{obj_key(cluster.obj)}' exists"]
            if cluster.exists()
            else []
        ),
        PRUNE_TIMEOUT_SEC,
        "the cluster's Kustomization wasn't deleted",
    )
    return applied


def workload_problems(workload_cluster: pykube.HTTPClient) -> list[str]:
    """The Deployments of the cluster's apps that are still in the workload cluster."""
    assertions = load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR).values()
    deployments = [
        a for file in assertions for a in file if a.get("kind") == "Deployment"
    ]
    return [
        f"Deployment '{obj_key(d)}' wasn't deleted from the workload cluster"
        for d in deployments
        if pykube.Deployment.objects(workload_cluster)
        .filter(namespace=d["metadata"]["namespace"])
        .get_or_none(name=d["metadata"]["name"])
        is not None
    ]
