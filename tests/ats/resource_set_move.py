"""U5: moving a running cluster to scheduled upgrades keeps its values and doesn't upgrade it.

docs/how-to/scheduled-upgrades-existing-cluster.md moves an ordinary cluster to the layout of the
scheduled-upgrades example, whose ResourceSet then takes the cluster's HelmRelease and
OCIRepository over. The check does that to capi-wc-name, the WC_NAME example, without a commit:
it suspends the cluster's Kustomization, which stands in for Flux letting go of the two objects
once the move is pushed, applies the provider and the ResourceSet that cluster_move builds from
the moved directory, with the range pinned to the release the cluster runs, and forces the
provider. The ResourceSet has to take both objects over with the cluster's `valuesFrom`, and
nothing helm-controller decides an upgrade on may change: the chart reference, the tag,
`valuesFrom` and `values`. The kind test never installs a cluster chart, so it can't see a Helm
revision; helm-controller v1.4.5 upgrades only on a changed chart or values
(`DetermineReleaseState`), which is what the unchanged specs stand for.

Afterwards it deletes the ResourceSet and the provider, which keep the two objects, as
`fluxcd.controlplane.io/prune: disabled` says, takes the ResourceSet's labels and annotation
off them, and resumes the Kustomization, which takes them back.
"""

from pathlib import Path

import pykube
from checks.kinds import OCIRepositoryCR
from checks.waits import fail_on_problems
from cluster_move import (
    copy_cluster,
    move,
    named,
    spec_changes,
    substitute,
    values_from_problems,
)
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


def taken_over_problems(obj: APIObject) -> list[str]:
    """Why `obj` isn't the ResourceSet's yet. The ResourceSet sets its labels in the same
    apply as the spec, so once they're there, the spec is what it rendered."""
    obj.reload()
    labels = obj.obj["metadata"].get("labels") or {}
    if labels.get("resourceset.fluxcd.controlplane.io/name") != MOVED_CLUSTER:
        return [f"{obj.kind} '{MOVED_CLUSTER}' isn't the ResourceSet's"]
    return []


def move_problems(api: pykube.HTTPClient, tmp_path: Path) -> list[str]:
    """Move the cluster; return how the specs of its HelmRelease and OCIRepository changed.

    helm-controller upgrades a release when its chart or its values change, so the same chart
    reference, tag, `valuesFrom` and `values` mean no upgrade. The kind test can't watch for
    one: it never installs a cluster chart, so there is no Helm revision to compare.
    """
    objects = [
        get(api, HelmReleaseCR, MOVED_CLUSTER),
        get(api, OCIRepositoryCR, MOVED_CLUSTER),
    ]
    before = {o.kind: o.obj["spec"] for o in objects}
    release = before["OCIRepository"]["ref"]["tag"]
    for obj in moved_objects(tmp_path, release):
        kind = (
            ResourceSetCR
            if obj["kind"] == "ResourceSet"
            else ResourceSetInputProviderCR
        )
        kind(api, obj).create()
    install_now(api, MOVED_PROVIDER, MOVED_CLUSTER)
    wait_until(
        lambda: [p for o in objects for p in taken_over_problems(o)],
        READY_TIMEOUT_SEC,
        "the ResourceSet didn't take the cluster over",
    )
    hr = objects[0].obj["spec"]
    problems = values_from_problems(
        before["HelmRelease"].get("valuesFrom") or [], hr.get("valuesFrom") or []
    )
    for o in objects:
        problems += spec_changes(o.kind, before[o.kind], o.obj["spec"], NAMESPACE)
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
