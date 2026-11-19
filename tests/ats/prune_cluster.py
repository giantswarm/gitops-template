"""P3: deleting a cluster's Kustomizations deletes what they applied, except the cluster.

When a cluster's Kustomizations go, the cluster's and the one of its secondary apps, because
their files are deleted from Git or by hand as the getting-started guides do, Flux deletes
everything they applied, except what has `kustomize.toolkit.fluxcd.io/prune: disabled`: the
cluster's HelmRelease stays.
"""

import pykube
from checks.assertion_files import WORKLOAD_CLUSTER_ASSERTIONS_DIR, load_assertions
from checks.conditions import obj_key
from flux_inventory import applied_deployments, inventory_keys
from flux_reconcile import suspend, wait_until
from prune_objects import (
    CLUSTER_KUSTOMIZATIONS,
    PRUNE_TIMEOUT_SEC,
    ROOT_KUSTOMIZATION,
)
from prune_source import kustomization


def delete_cluster_kustomizations(
    api: pykube.HTTPClient,
) -> set[tuple[str, str, str]]:
    """Delete the cluster's Kustomizations and wait until they're gone; return what they
    applied.

    The management cluster's Kustomization is suspended first, so it doesn't create them again.
    """
    suspend(kustomization(api, ROOT_KUSTOMIZATION))
    kustomizations = [kustomization(api, k) for k in CLUSTER_KUSTOMIZATIONS]
    applied = set().union(*(inventory_keys(k.obj) for k in kustomizations))
    for k in kustomizations:
        k.delete()
    wait_until(
        lambda: [
            f"Kustomization '{obj_key(k.obj)}' exists"
            for k in kustomizations
            if k.exists()
        ],
        PRUNE_TIMEOUT_SEC,
        "the cluster's Kustomizations weren't deleted",
    )
    return applied


def workload_problems(
    workload_cluster: pykube.HTTPClient, applied: set[tuple[str, str, str]]
) -> list[str]:
    """The Deployments of the apps the cluster's Kustomizations `applied` that are still in
    the workload cluster."""
    assertions = load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR).values()
    deployments = applied_deployments([a for file in assertions for a in file], applied)
    return [
        f"Deployment '{obj_key(d)}' wasn't deleted from the workload cluster"
        for d in deployments
        if pykube.Deployment.objects(workload_cluster)
        .filter(namespace=d["metadata"]["namespace"])
        .get_or_none(name=d["metadata"]["name"])
        is not None
    ]
