"""T1: the checks of tenancy_files, and the repository against them; they need no cluster."""

from pathlib import Path

import pytest
from tenancy_files import (
    MANAGEMENT_CLUSTERS_DIR,
    expected_namespace,
    is_management_cluster_file,
    repository_tenancy_problems,
    tenancy_problems,
)


def kustomization(
    namespace: str, source_namespace: str | None = None, **spec: object
) -> dict:
    source = {"kind": "GitRepository", "name": "your-repo"}
    if source_namespace is not None:
        source["namespace"] = source_namespace
    return {
        "metadata": {"name": "k", "namespace": namespace},
        "spec": {"serviceAccountName": "automation", "sourceRef": source, **spec},
    }


def test_repository_kustomizations_live_in_their_organization() -> None:
    assert repository_tenancy_problems() == []


def test_management_cluster_file() -> None:
    root = Path("/repo/management-clusters")
    assert is_management_cluster_file(root / "mc/mc.yaml", root)
    assert not is_management_cluster_file(root / "mc/organizations/o/o.yaml", root)
    assert not is_management_cluster_file(root / "mc/secrets/mc.yaml", root)


# the template's placeholder ORG_NAME stands for org-name
@pytest.mark.parametrize(
    ("file", "namespace"),
    [
        ("mc/mc.yaml", "default"),
        ("mc/organizations/a/workload-clusters/c.yaml", "org-a"),
        ("mc/organizations/ORG_NAME/c.yaml", "org-org-name"),
        ("mc/workload-clusters/c.yaml", None),
    ],
)
def test_expected_namespace(file: str, namespace: str | None) -> None:
    root = Path("/repo/management-clusters")
    assert expected_namespace(root / file, root) == namespace


def test_management_cluster_kustomization_in_default() -> None:
    assert tenancy_problems(kustomization("default"), "default") == []
    assert tenancy_problems(kustomization("org-a", "default"), "default") == [
        "Kustomization 'org-a/k' isn't in 'default'"
    ]


def test_cluster_kustomization_in_default() -> None:
    # runs as default/automation, which can write every organization's namespace
    assert tenancy_problems(kustomization("default"), None) == [
        "Kustomization 'default/k' isn't in an organization namespace"
    ]


def test_cluster_kustomization_in_organization() -> None:
    assert tenancy_problems(kustomization("org-a", "default"), "org-a") == []


def test_cluster_kustomization_without_source_namespace() -> None:
    # Flux would look for the GitRepository in org-a
    assert tenancy_problems(kustomization("org-a"), "org-a") == [
        "Kustomization 'org-a/k' doesn't name the namespace of its GitRepository"
    ]


def test_cluster_kustomization_in_another_organization() -> None:
    # runs as org-other/automation, which can't write org-a, where its clusters live
    assert tenancy_problems(kustomization("org-other", "default"), "org-a") == [
        "Kustomization 'org-other/k' isn't in 'org-a'"
    ]


# without one, it runs as kustomize-controller, which can write every namespace
@pytest.mark.parametrize("service_account", [None, "flux"])
def test_cluster_kustomization_not_run_as_automation(
    service_account: str | None,
) -> None:
    doc = kustomization("org-a", "default", serviceAccountName=service_account)
    assert tenancy_problems(doc, "org-a") == [
        "Kustomization 'org-a/k' doesn't run as 'automation'"
    ]


def test_kustomization_with_kubeconfig_needs_no_service_account() -> None:
    # it applies to its workload cluster as the kubeconfig's user
    doc = kustomization(
        "org-a",
        "default",
        kubeConfig={"secretRef": {"name": "c"}},
        serviceAccountName=None,
    )
    assert tenancy_problems(doc, "org-a") == []


def test_directory_has_kustomizations() -> None:
    assert MANAGEMENT_CLUSTERS_DIR.is_dir()
