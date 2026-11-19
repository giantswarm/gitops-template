"""T1: where the repository's Flux Kustomizations live, and so whose `automation`
ServiceAccount they run as; needs no cluster.

The management cluster's Kustomization, `management-clusters/<MC>/<MC>.yaml`, lives in
`default` and runs as `default/automation`. Every other Kustomization lives in the `org-*`
namespace of its organization, so its `serviceAccountName: automation` is that organization's
ServiceAccount. Its source, the GitRepository, stays in `default`, so it names that namespace.
"""

from collections.abc import Iterator
from pathlib import Path

import yaml

MANAGEMENT_CLUSTERS_DIR = (
    Path(__file__).resolve().parent / "../../management-clusters"
).resolve()
# the namespace of the GitRepository and of the management cluster's Kustomization
PLATFORM_NAMESPACE = "default"
ORGANIZATION_PREFIX = "org-"


def kustomizations(directory: Path) -> Iterator[tuple[Path, dict]]:
    """Every Flux Kustomization in the YAML files below `directory`, with its file."""
    for file in sorted(directory.rglob("*.yaml")):
        with file.open() as f:
            for doc in yaml.safe_load_all(f):
                if (
                    isinstance(doc, dict)
                    and doc.get("kind") == "Kustomization"
                    and doc.get("apiVersion", "").startswith(
                        "kustomize.toolkit.fluxcd.io/"
                    )
                ):
                    yield file, doc


def is_management_cluster_file(file: Path, directory: Path) -> bool:
    """Whether `file` is `<directory>/<MC>/<MC>.yaml`, the management cluster's Kustomization."""
    return file.parent.parent == directory and file.stem == file.parent.name


def tenancy_problems(doc: dict, management_cluster: bool) -> list[str]:
    """Why the Kustomization `doc` doesn't live where T1 says, if it doesn't."""
    meta = doc["metadata"]
    namespace = meta.get("namespace", "")
    key = f"Kustomization '{namespace}/{meta['name']}'"
    if management_cluster:
        if namespace != PLATFORM_NAMESPACE:
            return [f"{key} isn't in '{PLATFORM_NAMESPACE}'"]
        return []
    if not namespace.startswith(ORGANIZATION_PREFIX):
        return [f"{key} isn't in an organization namespace"]
    source = doc["spec"]["sourceRef"]
    if source.get("namespace", namespace) != PLATFORM_NAMESPACE:
        return [f"{key} doesn't name the namespace of its GitRepository"]
    return []


def repository_tenancy_problems(directory: Path = MANAGEMENT_CLUSTERS_DIR) -> list[str]:
    """T1 for every Kustomization below `directory`."""
    return [
        problem
        for file, doc in kustomizations(directory)
        for problem in tenancy_problems(
            doc, is_management_cluster_file(file, directory)
        )
    ]
