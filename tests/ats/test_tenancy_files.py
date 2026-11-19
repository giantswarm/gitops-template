"""T1: the checks of tenancy_files, and the repository against them; they need no cluster."""

from pathlib import Path

from tenancy_files import (
    MANAGEMENT_CLUSTERS_DIR,
    is_management_cluster_file,
    repository_tenancy_problems,
    tenancy_problems,
)


def kustomization(namespace: str, source_namespace: str | None = None) -> dict:
    source = {"kind": "GitRepository", "name": "your-repo"}
    if source_namespace is not None:
        source["namespace"] = source_namespace
    return {
        "metadata": {"name": "k", "namespace": namespace},
        "spec": {"serviceAccountName": "automation", "sourceRef": source},
    }


def test_repository_kustomizations_live_in_their_organization() -> None:
    assert repository_tenancy_problems() == []


def test_management_cluster_file() -> None:
    root = Path("/repo/management-clusters")
    assert is_management_cluster_file(root / "mc/mc.yaml", root)
    assert not is_management_cluster_file(root / "mc/organizations/o/o.yaml", root)
    assert not is_management_cluster_file(root / "mc/secrets/mc.yaml", root)


def test_management_cluster_kustomization_in_default() -> None:
    assert tenancy_problems(kustomization("default"), True) == []
    assert tenancy_problems(kustomization("org-a", "default"), True) == [
        "Kustomization 'org-a/k' isn't in 'default'"
    ]


def test_cluster_kustomization_in_default() -> None:
    # runs as default/automation, which can write every organization's namespace
    assert tenancy_problems(kustomization("default"), False) == [
        "Kustomization 'default/k' isn't in an organization namespace"
    ]


def test_cluster_kustomization_in_organization() -> None:
    assert tenancy_problems(kustomization("org-a", "default"), False) == []


def test_cluster_kustomization_without_source_namespace() -> None:
    # Flux would look for the GitRepository in org-a
    assert tenancy_problems(kustomization("org-a"), False) == [
        "Kustomization 'org-a/k' doesn't name the namespace of its GitRepository"
    ]


def test_directory_has_kustomizations() -> None:
    assert MANAGEMENT_CLUSTERS_DIR.is_dir()
