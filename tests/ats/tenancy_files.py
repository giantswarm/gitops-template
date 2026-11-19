"""T1: where the repository's Flux Kustomizations live, and so whose `automation`
ServiceAccount they run as; needs no cluster.

The management cluster's Kustomization, `management-clusters/<MC>/<MC>.yaml`, lives in
`default` and runs as `default/automation`. Every other Kustomization lives in the namespace
of its organization, `org-<org>` for a file below `<MC>/organizations/<org>/`, and runs as
`automation`, that organization's ServiceAccount. A Kustomization with a `kubeConfig` applies
to its workload cluster as the kubeconfig's user, so it needs no ServiceAccount. The source,
the GitRepository, stays in `default`, so a Kustomization elsewhere names that namespace.
"""

from collections.abc import Iterator
from pathlib import Path

import yaml
from automation_rbac import ORGANIZATION_PREFIX, SERVICE_ACCOUNT_NAME

# the namespace of the GitRepository and of the management cluster's Kustomization
from conftest import FLUX_OBJECTS_NAMESPACE

MANAGEMENT_CLUSTERS_DIR = (
    Path(__file__).resolve().parent / "../../management-clusters"
).resolve()


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


def expected_namespace(file: Path, directory: Path) -> str | None:
    """The namespace of the Kustomization in `file`: `default` for the management cluster's,
    `org-<org>` below `<MC>/organizations/<org>/`, None anywhere else."""
    if is_management_cluster_file(file, directory):
        return FLUX_OBJECTS_NAMESPACE
    parts = file.relative_to(directory).parts
    if len(parts) > 3 and parts[1] == "organizations":
        # the template's placeholder ORG_NAME stands for org-name
        return ORGANIZATION_PREFIX + parts[2].lower().replace("_", "-")
    return None


def namespace_problems(key: str, namespace: str, expected: str | None) -> list[str]:
    """Why `namespace` isn't `expected`, or not an organization's if nothing is expected."""
    if expected is None:
        if not namespace.startswith(ORGANIZATION_PREFIX):
            return [f"{key} isn't in an organization namespace"]
    elif namespace != expected:
        return [f"{key} isn't in '{expected}'"]
    return []


def tenancy_problems(doc: dict, expected: str | None) -> list[str]:
    """Why the Kustomization `doc`, which belongs in `expected`, doesn't live where T1 says."""
    meta, spec = doc["metadata"], doc["spec"]
    namespace = meta.get("namespace", "")
    key = f"Kustomization '{namespace}/{meta['name']}'"
    problems = namespace_problems(key, namespace, expected)
    if "kubeConfig" not in spec and spec.get("serviceAccountName") != (
        SERVICE_ACCOUNT_NAME
    ):
        problems.append(f"{key} doesn't run as '{SERVICE_ACCOUNT_NAME}'")
    if spec["sourceRef"].get("namespace", namespace) != FLUX_OBJECTS_NAMESPACE:
        problems.append(f"{key} doesn't name the namespace of its GitRepository")
    return problems


def repository_tenancy_problems(directory: Path = MANAGEMENT_CLUSTERS_DIR) -> list[str]:
    """T1 for every Kustomization below `directory`."""
    return [
        problem
        for file, doc in kustomizations(directory)
        for problem in tenancy_problems(doc, expected_namespace(file, directory))
    ]
