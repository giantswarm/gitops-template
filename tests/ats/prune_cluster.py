"""P3: deleting a cluster's Kustomizations deletes what they applied, except the cluster.

test_prune deletes the cluster as the getting-started guides do. It removes the cluster's
application team first, as docs/tutorials/advanced/teams.md describes: the team's Kustomization
deletes its workload from the workload cluster as the organisation's automation ServiceAccount,
through a RoleBinding the cluster's -direct Kustomization applies, so the team has to go before
the RoleBinding does. Then it deletes the cluster's three Kustomizations, the cluster's, the one
of its secondary apps and the -direct one, as deleting their files from Git does, and waits
until the first two are gone, then the -direct one. Flux deletes everything they applied, except
what has `kustomize.toolkit.fluxcd.io/prune: disabled`: the cluster's HelmRelease and
OCIRepository stay. The -direct Kustomization deletes what it applied from the workload cluster,
which it reaches through the cluster's kubeconfig Secret, so it has to be gone before the
cluster is.
"""

import pykube
from checks.assertion_files import WORKLOAD_CLUSTER_ASSERTIONS_DIR, load_assertions
from checks.conditions import obj_key
from flux_inventory import applied_deployments, inventory_keys
from flux_reconcile import request_reconcile, suspend, wait_until
from prune_objects import (
    APPS_KUSTOMIZATION,
    CLUSTER_KUSTOMIZATIONS,
    DIRECT_KUSTOMIZATION,
    ORGANIZATION_KUSTOMIZATION,
    PRUNE_TIMEOUT_SEC,
    PRUNED_OBJECTS,
    ROOT_KUSTOMIZATION,
    TEAM_OBJECTS,
    TEAM_WORKLOAD,
    UNINSTALL_TIMEOUT_SEC,
    deleted_problems,
    get_object,
)
from prune_patches import delete_patches
from prune_source import kustomization
from pykube.objects import APIObject

# (kind, namespace, name) of an object, in the management cluster or the workload cluster
ObjectKey = tuple[str, str, str]


def deployment_problems(
    workload_cluster: pykube.HTTPClient, namespace: str, name: str
) -> list[str]:
    """Whether the Deployment `namespace/name` is still in the workload cluster."""
    deployment = (
        pykube.Deployment.objects(workload_cluster)
        .filter(namespace=namespace)
        .get_or_none(name=name)
    )
    if deployment is None:
        return []
    return [f"Deployment '{namespace}/{name}' wasn't deleted from the workload cluster"]


def remove_team(api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient) -> None:
    """Remove the cluster's application team, as deleting its directory in the cluster's
    teams/ does, and wait until its Kustomization and its workload are gone.

    The apps Kustomization already drops the app check_removed_files removes, so its patches
    keep doing that.
    """
    apps = kustomization(api, APPS_KUSTOMIZATION)
    apps.patch({"spec": {"patches": delete_patches(PRUNED_OBJECTS + TEAM_OBJECTS)}})
    request_reconcile(apps)
    wait_until(
        lambda: deleted_problems(api, TEAM_OBJECTS)
        + deployment_problems(workload_cluster, *TEAM_WORKLOAD),
        UNINSTALL_TIMEOUT_SEC,
        "the application team wasn't removed",
    )


def gone_problems(kustomizations: list[APIObject]) -> list[str]:
    """The `kustomizations` that still exist."""
    return [
        f"Kustomization '{obj_key(k.obj)}' exists" for k in kustomizations if k.exists()
    ]


def delete_cluster_kustomizations(
    api: pykube.HTTPClient,
) -> tuple[set[ObjectKey], set[ObjectKey]]:
    """Delete the cluster's Kustomizations, the -direct one with them, and wait until they're
    gone, in the getting-started guides' order; return what the cluster's two applied to the
    management cluster, and what the -direct one applied to the workload cluster.

    The management cluster's Kustomization, and the organisation's namespace Kustomization, which
    applies all three, are suspended first, so they don't create them again.
    """
    suspend(kustomization(api, ROOT_KUSTOMIZATION))
    suspend(kustomization(api, ORGANIZATION_KUSTOMIZATION))
    kustomizations = [kustomization(api, k) for k in CLUSTER_KUSTOMIZATIONS]
    direct = kustomization(api, DIRECT_KUSTOMIZATION)
    applied = set().union(*(inventory_keys(k.obj) for k in kustomizations))
    direct_applied = inventory_keys(direct.obj)
    for k in [*kustomizations, direct]:
        k.delete()
    wait_until(
        lambda: gone_problems(kustomizations),
        PRUNE_TIMEOUT_SEC,
        "the cluster's Kustomizations weren't deleted",
    )
    wait_until(
        lambda: gone_problems([direct]),
        PRUNE_TIMEOUT_SEC,
        "the cluster's -direct Kustomization wasn't deleted",
    )
    return applied, direct_applied


def workload_problems(
    workload_cluster: pykube.HTTPClient, applied: set[ObjectKey]
) -> list[str]:
    """The Deployments of the apps the cluster's Kustomizations `applied` that are still in
    the workload cluster."""
    assertions = load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR).values()
    deployments = applied_deployments([a for file in assertions for a in file], applied)
    return [
        problem
        for d in deployments
        for problem in deployment_problems(
            workload_cluster, d["metadata"]["namespace"], d["metadata"]["name"]
        )
    ]


def direct_problems(
    workload_cluster: pykube.HTTPClient, direct_applied: set[ObjectKey]
) -> list[str]:
    """The objects the -direct Kustomization applied that are still in the workload
    cluster."""
    return [
        f"{kind} '{namespace}/{name}' wasn't deleted from the workload cluster"
        for kind, namespace, name in sorted(direct_applied)
        if get_object(workload_cluster, kind, namespace, name) is not None
    ]
