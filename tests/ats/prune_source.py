"""P1, P2: removing files from the source the kind test reads, without a push.

The kind test reads a branch it can't push to. The GitRepository's `spec.ignore` leaves the
files out of the artifact Flux applies instead, as if they were deleted from Git.
"""

import pykube
from conftest import FLUX_GIT_REPO_NAME, FLUX_OBJECTS_NAMESPACE
from flux_inventory import inventory_keys
from flux_reconcile import repo_problems, request_reconcile, wait_until
from prune_objects import (
    CLUSTER_KUSTOMIZATION,
    PROTECTED_OBJECTS,
    PRUNE_TIMEOUT_SEC,
    PRUNED_OBJECTS,
    ROOT_KUSTOMIZATION,
)
from pykube.objects import APIObject
from pytest_helm_charts.flux.git_repository import GitRepositoryCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from test_flux_objects import obj_key


def git_repository(api: pykube.HTTPClient) -> APIObject:
    return (
        GitRepositoryCR.objects(api)
        .filter(namespace=FLUX_OBJECTS_NAMESPACE)
        .get(name=FLUX_GIT_REPO_NAME)
    )


def kustomization(api: pykube.HTTPClient, key: tuple[str, str]) -> APIObject:
    namespace, name = key
    return KustomizationCR.objects(api).filter(namespace=namespace).get(name=name)


def inventory_problems(kustomizations: list[APIObject]) -> list[str]:
    """The Kustomizations whose inventory still lists objects of the removed files."""
    removed = set(PRUNED_OBJECTS + PROTECTED_OBJECTS)
    problems = []
    for k in kustomizations:
        k.reload()
        left = sorted(inventory_keys(k.obj) & removed)
        if left:
            problems.append(
                f"Kustomization '{obj_key(k.obj)}' still has removed objects: {left}"
            )
    return problems


def remove_from_source(api: pykube.HTTPClient, ignore: str) -> None:
    """Leave the files `ignore` matches out of the GitRepository's artifact, as if they were
    deleted from Git, and wait until the Kustomizations that applied them have applied the
    new artifact.
    """
    repo = git_repository(api)
    repo.patch({"spec": {"ignore": ignore}})
    request_reconcile(repo)
    wait_until(
        lambda: repo_problems(repo), PRUNE_TIMEOUT_SEC, "the GitRepository isn't ready"
    )

    # The new artifact has a new digest but the same revision, the commit, and
    #  kustomize-controller only reacts to a new revision by itself. Without the request, the
    #  Kustomizations would apply it at their next interval.
    kustomizations = [
        kustomization(api, k) for k in (ROOT_KUSTOMIZATION, CLUSTER_KUSTOMIZATION)
    ]
    for k in kustomizations:
        request_reconcile(k)
    wait_until(
        lambda: inventory_problems(kustomizations),
        PRUNE_TIMEOUT_SEC,
        "the Kustomizations haven't applied the removal",
    )


def restore_source(api: pykube.HTTPClient) -> None:
    """Put the files remove_from_source left out back into the artifact."""
    repo = git_repository(api)
    repo.patch({"spec": {"ignore": None}})
    request_reconcile(repo)
