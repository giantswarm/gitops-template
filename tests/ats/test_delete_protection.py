"""Removing the deletion protection of a cluster that a ResourceSet renders, as
docs/how-to/delete-cluster.md does it: its patch on the ResourceSet has to take the
`giantswarm.io/prevent-deletion` label off the rendered OCIRepository and HelmRelease, and set
`preventDeletion` to false in the values the release reads. Checks of the how-to's patch on a
copy of the WC_NAME_SCHEDULED_UPGRADES example; they need no cluster, only kubectl."""

import re
from pathlib import Path

import yaml
from cluster_move import EXAMPLE_DIR, RESOURCE_SET_TARGET, copy_cluster, named
from helm_values import merged_values
from root_build import REPO_DIR, build

HOW_TO = REPO_DIR / "docs" / "how-to" / "delete-cluster.md"
PATCH_FILE = "patch_remove_protection.yaml"
LABEL = "giantswarm.io/prevent-deletion"
# the heredoc in the how-to that writes the patch, indented as a list item's code block
HEREDOC = re.compile(
    r"cat <<'EOF' > \$\{WC_DIR\}/cluster/"
    + re.escape(PATCH_FILE)
    + r"\n(.*?)\n\s*EOF\n",
    re.DOTALL,
)
# the management cluster gives every organisation this ConfigMap; the test has none
INSTALLATION_VALUES = {"data": {"values.yaml": ""}}


def how_to_patch() -> str:
    """The patch the how-to writes, without the code block's indentation."""
    found = HEREDOC.search(HOW_TO.read_text())
    assert found, f"{HOW_TO.name} writes no {PATCH_FILE}"
    return "\n".join(line.removeprefix("    ") for line in found.group(1).splitlines())


def rendered(objects: list[dict], kind: str) -> dict:
    resource_set = named(objects, "ResourceSet")
    return next(r for r in resource_set["spec"]["resources"] if r["kind"] == kind)


def prevent_deletion(objects: list[dict]) -> object:
    """`global.metadata.preventDeletion` in the values of the rendered HelmRelease."""
    config_maps = {
        o["metadata"]["name"]: o for o in objects if o["kind"] == "ConfigMap"
    }
    config_maps["cluster-app-installation-values"] = INSTALLATION_VALUES

    def lookup(kind: str, namespace: str, name: str) -> dict | None:
        return config_maps.get(name) if kind == "ConfigMap" else None

    values = merged_values(rendered(objects, "HelmRelease"), lookup)
    return values["global"]["metadata"]["preventDeletion"]


def labelled(objects: list[dict]) -> list[str]:
    return [
        kind
        for kind in ("OCIRepository", "HelmRelease")
        if LABEL in rendered(objects, kind)["metadata"].get("labels", {})
    ]


def test_example_is_protected(tmp_path: Path) -> None:
    objects = build(copy_cluster(tmp_path, EXAMPLE_DIR))
    assert labelled(objects) == ["OCIRepository", "HelmRelease"]
    assert prevent_deletion(objects) is True


def test_how_to_patch_removes_the_protection(tmp_path: Path) -> None:
    cluster_dir = copy_cluster(tmp_path, EXAMPLE_DIR)
    (cluster_dir / PATCH_FILE).write_text(how_to_patch())
    path = cluster_dir / "kustomization.yaml"
    kustomization = yaml.safe_load(path.read_text())
    kustomization["patches"].append(
        {"path": PATCH_FILE, "target": dict(RESOURCE_SET_TARGET)}
    )
    path.write_text(yaml.safe_dump(kustomization, sort_keys=False))
    objects = build(cluster_dir)
    assert labelled(objects) == []
    assert prevent_deletion(objects) is False
