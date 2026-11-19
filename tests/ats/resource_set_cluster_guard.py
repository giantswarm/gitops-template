"""U4: neither losing the version nor deleting the ResourceSet deletes the cluster.

The cluster example's ResourceSet renders the cluster's OCIRepository and HelmRelease, and
deleting the HelmRelease deletes the cluster. Its `dependsOn` holds it as the app example's
does: the check takes the version away in the same three ways as resource_set_guard. Then it
deletes the ResourceSet, as removing its file from Git does; `fluxcd.controlplane.io/prune:
disabled` has to keep both objects.

The cluster's Kustomization is suspended meanwhile. Resuming it puts the provider and the
ResourceSet back, and the ResourceSet takes the objects over again.
"""

import pykube
from checks.kinds import OCIRepositoryCR
from checks.waits import fail_on_problems
from flux_reconcile import suspend, wait_until
from prune_source import kustomization
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from resource_set_guard import lose_version
from resource_set_objects import (
    CLUSTER_KUSTOMIZATION,
    CLUSTER_NAME,
    CLUSTER_PROVIDER,
    CLUSTER_RESOURCE_SET,
    HANDLED_TIMEOUT_SEC,
    NAMESPACE,
    ResourceSetCR,
    get,
    install_now,
    resume,
)

CLUSTER_KINDS = {"HelmRelease": HelmReleaseCR, "OCIRepository": OCIRepositoryCR}


def cluster_problems(api: pykube.HTTPClient) -> list[str]:
    """The cluster's objects that are deleted or being deleted."""
    problems = []
    for kind, cls in CLUSTER_KINDS.items():
        query = cls.objects(api).filter(namespace=NAMESPACE)
        obj = query.get_or_none(name=CLUSTER_NAME)
        if obj is None:
            problems.append(f"{kind} '{NAMESPACE}/{CLUSTER_NAME}' was deleted")
        elif obj.obj["metadata"].get("deletionTimestamp"):
            problems.append(f"{kind} '{NAMESPACE}/{CLUSTER_NAME}' is being deleted")
    return problems


def delete_resource_set(api: pykube.HTTPClient) -> list[str]:
    """Delete the ResourceSet; return how the cluster's objects didn't stay."""
    rset = get(api, ResourceSetCR, CLUSTER_RESOURCE_SET)
    rset.delete()
    wait_until(
        lambda: [f"'{CLUSTER_RESOURCE_SET}' exists"] if rset.exists() else [],
        HANDLED_TIMEOUT_SEC,
        "the ResourceSet wasn't deleted",
    )
    return [f"the ResourceSet is deleted: {p}" for p in cluster_problems(api)]


def check_cluster_input_loss(api: pykube.HTTPClient) -> None:
    """U4, then Flux puts the provider and the ResourceSet back."""
    cluster = kustomization(api, CLUSTER_KUSTOMIZATION)
    suspend(cluster)
    try:
        problems = lose_version(
            api,
            CLUSTER_PROVIDER,
            CLUSTER_RESOURCE_SET,
            lambda: cluster_problems(api),
        )
        problems += delete_resource_set(api)
        fail_on_problems(problems, "the cluster wasn't kept")
    finally:
        resume(cluster)
        install_now(api, CLUSTER_PROVIDER, CLUSTER_RESOURCE_SET)
