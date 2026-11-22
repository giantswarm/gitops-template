"""U5: moving a running cluster to scheduled upgrades keeps its values and doesn't upgrade it.

docs/how-to/scheduled-upgrades-existing-cluster.md moves an ordinary cluster to the layout of the
scheduled-upgrades example, whose ResourceSet then takes the cluster's HelmRelease and
OCIRepository over. The check does that to capi-wc-name, the WC_NAME example, without a commit:
it suspends the cluster's Kustomization, which stands in for Flux letting go of the two objects
once the move is pushed, applies the provider and the ResourceSet that cluster_move builds from
the moved directory, with the range pinned to the release the cluster runs, and forces the
provider. The ResourceSet has to take both objects over with the cluster's `valuesFrom`, and
helm-controller mustn't upgrade the release.

Afterwards it deletes the ResourceSet and the provider, which keep the two objects, as
`fluxcd.controlplane.io/prune: disabled` says, takes the ResourceSet's labels and annotation
off them, and resumes the Kustomization, which takes them back.
"""

from pathlib import Path

import pykube
from checks.conditions import is_ready, not_ready_reason
from checks.kinds import OCIRepositoryCR
from checks.waits import fail_on_problems
from cluster_move import copy_cluster, move, named, substitute, values_from_problems
from flux_reconcile import suspend, wait_until
from prune_source import kustomization
from pykube.objects import APIObject
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from resource_set_objects import (
    HANDLED_TIMEOUT_SEC,
    NAMESPACE,
    READY_TIMEOUT_SEC,
    ResourceSetCR,
    ResourceSetInputProviderCR,
    get,
    install_now,
    resume,
)
from root_build import build

MOVED_CLUSTER = "capi-wc-name"
MOVED_KUSTOMIZATION = (NAMESPACE, "mc-name-clusters-capi-wc-name")
MOVED_PROVIDER = f"{MOVED_CLUSTER}-release"
# what the cluster's Kustomization substitutes in the moved directory
VARIABLES = {"cluster_name": MOVED_CLUSTER, "organization": "org-name"}
# what the ResourceSet puts on the objects it renders
RESOURCE_SET_MARKS = {
    "labels": {
        "resourceset.fluxcd.controlplane.io/name": None,
        "resourceset.fluxcd.controlplane.io/namespace": None,
    },
    "annotations": {"fluxcd.controlplane.io/prune": None},
}


def moved_objects(tmp_path: Path, release: str) -> list[dict]:
    """The provider and the ResourceSet of the moved cluster, the provider's range pinned to
    `release`, as the how-to's first step pins it."""
    cluster_dir = copy_cluster(tmp_path)
    move(cluster_dir)
    objects = substitute(build(cluster_dir), VARIABLES)
    provider = named(objects, "ResourceSetInputProvider", MOVED_PROVIDER)
    provider["spec"]["filter"]["semver"] = release
    return [provider, named(objects, "ResourceSet", MOVED_CLUSTER)]


def release_version(hr: dict) -> int | None:
    """The revision of the Helm release the HelmRelease last installed or upgraded."""
    history = (hr.get("status") or {}).get("history") or []
    return history[0].get("version") if history else None


def taken_over_problems(obj: APIObject) -> list[str]:
    """Why `obj` isn't the ResourceSet's yet, or helm-controller hasn't reconciled its spec."""
    obj.reload()
    labels = obj.obj["metadata"].get("labels") or {}
    if labels.get("resourceset.fluxcd.controlplane.io/name") != MOVED_CLUSTER:
        return [f"{obj.kind} '{MOVED_CLUSTER}' isn't the ResourceSet's"]
    status = obj.obj.get("status") or {}
    if status.get("observedGeneration") != obj.obj["metadata"][
        "generation"
    ] or not is_ready(obj.obj):
        return [f"{obj.kind} '{MOVED_CLUSTER}': {not_ready_reason(obj.obj)}"]
    return []


def move_problems(api: pykube.HTTPClient, tmp_path: Path) -> list[str]:
    """Move the cluster; return how its HelmRelease changed."""
    hr = get(api, HelmReleaseCR, MOVED_CLUSTER)
    before = hr.obj["spec"].get("valuesFrom") or []
    version = release_version(hr.obj)
    release = get(api, OCIRepositoryCR, MOVED_CLUSTER).obj["spec"]["ref"]["tag"]
    for obj in moved_objects(tmp_path, release):
        kind = (
            ResourceSetCR
            if obj["kind"] == "ResourceSet"
            else ResourceSetInputProviderCR
        )
        kind(api, obj).create()
    install_now(api, MOVED_PROVIDER, MOVED_CLUSTER)
    source = get(api, OCIRepositoryCR, MOVED_CLUSTER)
    wait_until(
        lambda: taken_over_problems(hr) + taken_over_problems(source),
        READY_TIMEOUT_SEC,
        "the ResourceSet didn't take the cluster over",
    )
    problems = values_from_problems(before, hr.obj["spec"].get("valuesFrom") or [])
    if release_version(hr.obj) != version:
        problems.append(
            f"the move upgraded the release from revision {version} to "
            f"{release_version(hr.obj)}"
        )
    return problems


def delete_and_wait(obj: APIObject) -> None:
    obj.delete()
    wait_until(
        lambda: [f"{obj.kind} '{obj.name}' exists"] if obj.exists() else [],
        HANDLED_TIMEOUT_SEC,
        f"the {obj.kind} wasn't deleted",
    )


def undo_move(api: pykube.HTTPClient) -> None:
    """Delete the ResourceSet and the provider, and take the ResourceSet's marks off the
    objects it kept, so that the cluster's Kustomization owns them alone again."""
    for kind, name in (
        (ResourceSetCR, MOVED_CLUSTER),
        (ResourceSetInputProviderCR, MOVED_PROVIDER),
    ):
        obj = kind.objects(api).filter(namespace=NAMESPACE).get_or_none(name=name)
        if obj is not None:
            delete_and_wait(obj)
    for kind in (HelmReleaseCR, OCIRepositoryCR):
        get(api, kind, MOVED_CLUSTER).patch({"metadata": RESOURCE_SET_MARKS})


def check_move(api: pykube.HTTPClient, tmp_path: Path) -> None:
    """U5, then the cluster's Kustomization owns the cluster again."""
    cluster = kustomization(api, MOVED_KUSTOMIZATION)
    suspend(cluster)
    try:
        fail_on_problems(move_problems(api, tmp_path), "changes by the move")
    finally:
        undo_move(api)
        resume(cluster)
