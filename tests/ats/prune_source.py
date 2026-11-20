"""P1, P2: removing files from what the kind test applies, without a push.

The kind test reads a branch it can't push to. The GitRepository's `spec.ignore` leaves the
files out of the artifact Flux applies instead, as if they were deleted from Git. A file that a
kustomization.yaml lists can't be left out that way, as the list would name a file that's gone:
`$patch: delete` patches in the Kustomization's `spec.patches` drop its objects instead. P2
leaves out the Organization, which the organisation's kustomization.yaml lists, on purpose: the
management cluster's Kustomization then fails to build and prunes nothing.
"""

import pykube
from checks.conditions import obj_key
from conftest import FLUX_GIT_REPO_NAME, FLUX_OBJECTS_NAMESPACE
from flux_inventory import build_failure_problems, inventory_keys
from flux_reconcile import repo_problems, request_reconcile, wait_until
from prune_objects import (
    APPS_KUSTOMIZATION,
    KEPT_BY_FAILED_BUILD,
    PRUNE_TIMEOUT_SEC,
    PRUNED_OBJECTS,
    ROOT_KUSTOMIZATION,
)
from pykube.objects import APIObject
from pytest_helm_charts.flux.git_repository import GitRepositoryCR
from pytest_helm_charts.flux.kustomization import KustomizationCR


def git_repository(api: pykube.HTTPClient) -> APIObject:
    return (
        GitRepositoryCR.objects(api)
        .filter(namespace=FLUX_OBJECTS_NAMESPACE)
        .get(name=FLUX_GIT_REPO_NAME)
    )


def kustomization(api: pykube.HTTPClient, key: tuple[str, str]) -> APIObject:
    namespace, name = key
    return KustomizationCR.objects(api).filter(namespace=namespace).get(name=name)


def inventory_problems(apps: APIObject) -> list[str]:
    """P1: whether the apps Kustomization's inventory still lists objects of the removed app."""
    apps.reload()
    left = sorted(inventory_keys(apps.obj) & set(PRUNED_OBJECTS))
    if left:
        return [
            f"Kustomization '{obj_key(apps.obj)}' still has removed objects: {left}"
        ]
    return []


def root_problems(root: APIObject) -> list[str]:
    """P2: why the management cluster's Kustomization doesn't report that it can't build the
    organisation, or no longer lists what it applied from it, if so."""
    root.reload()
    return build_failure_problems(root.obj, set(KEPT_BY_FAILED_BUILD))


def remove_from_source(
    api: pykube.HTTPClient, ignore: str, patches: list[dict]
) -> None:
    """Leave the files `ignore` matches out of the GitRepository's artifact, as if they were
    deleted from Git, drop what `patches` delete from what the apps Kustomization builds, and
    wait until the apps Kustomization has applied the change and the management cluster's
    reports that it can't build without the files.
    """
    repo = git_repository(api)
    apps = kustomization(api, APPS_KUSTOMIZATION)
    apps.patch({"spec": {"patches": patches}})
    repo.patch({"spec": {"ignore": ignore}})
    request_reconcile(repo)
    wait_until(
        lambda: repo_problems(repo), PRUNE_TIMEOUT_SEC, "the GitRepository isn't ready"
    )

    # The new artifact has a new digest but the same revision, the commit, and
    #  kustomize-controller only reacts to a new revision by itself. Without the request, the
    #  Kustomizations would apply it at their next interval.
    root = kustomization(api, ROOT_KUSTOMIZATION)
    for k in (root, apps):
        request_reconcile(k)
    wait_until(
        lambda: inventory_problems(apps),
        PRUNE_TIMEOUT_SEC,
        "the apps Kustomization hasn't applied the removal",
    )
    wait_until(
        lambda: root_problems(root),
        PRUNE_TIMEOUT_SEC,
        "the management cluster's Kustomization doesn't report the failed build",
    )


def restore_source(api: pykube.HTTPClient) -> None:
    """Put the files remove_from_source left out back into the artifact. It doesn't bring back
    the cluster Kustomizations check_removed_cluster deletes, which is why test_prune runs last.
    """
    repo = git_repository(api)
    repo.patch({"spec": {"ignore": None}})
    request_reconcile(repo)
    namespace, name = APPS_KUSTOMIZATION
    apps = (
        KustomizationCR.objects(api).filter(namespace=namespace).get_or_none(name=name)
    )
    if apps is not None:
        apps.patch({"spec": {"patches": None}})
