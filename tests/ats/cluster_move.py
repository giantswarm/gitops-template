"""Moving a running cluster to scheduled upgrades, as
docs/how-to/scheduled-upgrades-existing-cluster.md does it, on a copy of a cluster directory.

The move copies the files of the WC_NAME_SCHEDULED_UPGRADES example into the cluster's
`cluster/` directory and lists them in its `kustomization.yaml`. The example's ResourceSet
renders the cluster's HelmRelease, and a patch drops the base's. A patch of the cluster's own
that targets the base's HelmRelease would then match nothing, and kustomize says nothing about a
patch that matches nothing, so the move points each of them at the ResourceSet instead: the
example's `patch_cluster_userconfig.yaml` appends the cluster's own values to the HelmRelease
the ResourceSet renders.
"""

import copy
import re
import shutil
from pathlib import Path

import yaml
from repository_gates import WORKLOAD_CLUSTERS_DIR
from root_build import REPO_DIR

# the ordinary cluster the how-to moves, and the example it moves it to
CLUSTER_DIR = WORKLOAD_CLUSTERS_DIR / "WC_NAME" / "cluster"
EXAMPLE_DIR = WORKLOAD_CLUSTERS_DIR / "WC_NAME_SCHEDULED_UPGRADES" / "cluster"
# what the cluster directories refer to above themselves
SHARED_DIRS = ("bases",)
# the files the how-to copies from the example; the last replaces the cluster's own
ADDED_RESOURCES = ("release-input-provider.yaml", "cluster-resource-set.yaml")
DELETE_PATCH = "patch_delete_base_cluster.yaml"
USERCONFIG_PATCH = "patch_cluster_userconfig.yaml"
MOVED_FILES = (*ADDED_RESOURCES, DELETE_PATCH, USERCONFIG_PATCH)
# the name the cluster's HelmRelease and its ResourceSet have before `postBuild`, as a
#  kustomize target, which reads names as regular expressions
CLUSTER_TARGET_NAME = r"\${cluster_name}"
CLUSTER_NAME = "${cluster_name}"
RESOURCE_SET_TARGET = {
    "group": "fluxcd.controlplane.io",
    "kind": "ResourceSet",
    "name": CLUSTER_TARGET_NAME,
}
# the variables Flux's `postBuild` substitutes, as `${name}`
VARIABLE = re.compile(r"\$\{(\w+)\}")


def copy_cluster(tmp_path: Path, cluster_dir: Path = CLUSTER_DIR) -> Path:
    """Copy `cluster_dir` and what it refers to into `tmp_path`, at the same place relative to
    the repository; return the copy of `cluster_dir`."""
    for name in SHARED_DIRS:
        shutil.copytree(REPO_DIR / name, tmp_path / name)
    copy = tmp_path / cluster_dir.relative_to(REPO_DIR)
    shutil.copytree(cluster_dir, copy)
    return copy


def move(cluster_dir: Path, retarget: bool = True) -> None:
    """Move the cluster in `cluster_dir` to the example's layout, as the how-to does: copy the
    example's files, list them, and point the patch of the cluster's own values at the
    ResourceSet, unless `retarget` is False."""
    for name in MOVED_FILES:
        shutil.copy(EXAMPLE_DIR / name, cluster_dir / name)
    path = cluster_dir / "kustomization.yaml"
    kustomization = yaml.safe_load(path.read_text())
    kustomization["resources"] += list(ADDED_RESOURCES)
    patches = kustomization.get("patches") or []
    if retarget:
        for patch in patches:
            if patch.get("path") == USERCONFIG_PATCH:
                patch["target"] = dict(RESOURCE_SET_TARGET)
    kustomization["patches"] = [{"path": DELETE_PATCH}, *patches]
    path.write_text(yaml.safe_dump(kustomization, sort_keys=False))


class NotOneError(LookupError):
    """The build has no object, or more than one, where the move needs exactly one."""

    def __init__(self, count: int, what: str) -> None:
        super().__init__(f"{count} {what} in the build, not one")


def named(objects: list[dict], kind: str, name: str = CLUSTER_NAME) -> dict:
    found = [
        o for o in objects if o.get("kind") == kind and o["metadata"]["name"] == name
    ]
    if len(found) != 1:
        raise NotOneError(len(found), f"{kind} objects named '{name}'")
    return found[0]


def base_values_from(objects: list[dict]) -> list[dict]:
    """The `valuesFrom` of the cluster's HelmRelease, as the cluster base renders it."""
    return named(objects, "HelmRelease")["spec"].get("valuesFrom") or []


def rendered_values_from(objects: list[dict]) -> list[dict]:
    """The `valuesFrom` of the HelmRelease the cluster's ResourceSet renders."""
    resource_set = named(objects, "ResourceSet")
    releases = [
        r for r in resource_set["spec"]["resources"] if r.get("kind") == "HelmRelease"
    ]
    if len(releases) != 1:
        raise NotOneError(len(releases), "HelmReleases in the ResourceSet")
    return releases[0]["spec"].get("valuesFrom") or []


def values_from_problems(before: list[dict], after: list[dict]) -> list[str]:
    """How the rendered `valuesFrom`, `after`, differs from the cluster's, `before`: an entry
    it lacks, or the entries in another order. Flux merges them in order."""
    problems = [
        f"the rendered HelmRelease lacks the valuesFrom entry {e.get('kind')} '{e.get('name')}'"
        for e in before
        if e not in after
    ]
    if not problems and before != after:
        problems.append(
            "the rendered HelmRelease merges the valuesFrom entries in another order: "
            f"{[e.get('name') for e in after]}, not {[e.get('name') for e in before]}"
        )
    return problems


def substitute(objects: list[dict], variables: dict[str, str]) -> list[dict]:
    """`objects` with the `${name}` variables replaced, as Flux's `postBuild` does."""

    def replace(match: re.Match) -> str:
        return variables.get(match.group(1), match.group(0))

    return [
        yaml.safe_load(VARIABLE.sub(replace, yaml.safe_dump(o, sort_keys=False)))
        for o in objects
    ]


def spec_changes(kind: str, before: dict, after: dict, namespace: str) -> list[str]:
    """How the live `spec` of the cluster's `kind` object changed when the ResourceSet took it
    over. A `chartRef.namespace` that names the HelmRelease's own `namespace` means the same as
    none, which is how the ResourceSet renders it."""

    def normal(spec: dict) -> dict:
        spec = copy.deepcopy(spec)
        chart_ref = spec.get("chartRef") or {}
        if kind == "HelmRelease" and chart_ref.get("namespace") == namespace:
            del chart_ref["namespace"]
        return spec

    b, a = normal(before), normal(after)
    return [
        f"{kind} spec.{key} changed from {b.get(key)!r} to {a.get(key)!r}"
        for key in sorted(set(b) | set(a))
        if b.get(key) != a.get(key)
    ]
