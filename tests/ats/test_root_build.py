"""The management cluster's root Kustomization has to apply on a new management cluster, where no
organisation namespace exists yet. Checks of root_build and of the repository's root build; they
need no cluster, only kubectl."""

from pathlib import Path

import pytest
from root_build import (
    MC_DIR,
    ORGANIZATION_NAMESPACE_LABEL,
    REPO_DIR,
    build,
    generated_resources,
    misplaced_objects,
    namespace_build_problems,
    organization_namespace_problems,
)

ORGANIZATION = {
    "apiVersion": "security.giantswarm.io/v1alpha1",
    "kind": "Organization",
    "metadata": {"name": "acme"},
}


def kustomization(name: str, namespace: str = "default", **spec: object) -> dict:
    return {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": name, "namespace": namespace},
        "spec": spec,
    }


def organization_kustomization(target: str, organization: str = "acme") -> dict:
    k = kustomization(
        "mc-organization-acme",
        targetNamespace=target,
        postBuild={"substitute": {"organization": organization}},
    )
    k["metadata"]["labels"] = {ORGANIZATION_NAMESPACE_LABEL: "true"}
    return k


def test_misplaced_objects_allows_organizations_and_default() -> None:
    assert misplaced_objects([ORGANIZATION, kustomization("a")]) == []


def test_misplaced_objects_names_objects_in_other_namespaces() -> None:
    alert = {"kind": "Alert", "metadata": {"name": "a", "namespace": "org-acme"}}
    assert misplaced_objects([alert]) == ["Alert 'org-acme/a'"]


def test_misplaced_objects_names_other_objects_without_a_namespace() -> None:
    role = {"kind": "ClusterRole", "metadata": {"name": "r"}}
    assert misplaced_objects([role]) == ["ClusterRole 'r'"]


def test_organization_namespace_problems_none() -> None:
    objects = [ORGANIZATION, organization_kustomization("org-acme")]
    assert organization_namespace_problems(objects) == []


def test_organization_namespace_problems_other_target() -> None:
    objects = [ORGANIZATION, organization_kustomization("org-ORG_NAME")]
    assert organization_namespace_problems(objects) == [
        "Kustomization 'default/mc-organization-acme' applies into 'org-ORG_NAME', "
        "not into 'org-acme'"
    ]


def test_organization_namespace_problems_unknown_organization() -> None:
    objects = [organization_kustomization("org-acme")]
    assert organization_namespace_problems(objects) == [
        "Kustomization 'default/mc-organization-acme' applies the namespace of 'acme', "
        "which has no Organization in the build"
    ]


def test_organization_namespace_problems_without_any() -> None:
    assert organization_namespace_problems([ORGANIZATION]) == [
        f"No Kustomization with the label '{ORGANIZATION_NAMESPACE_LABEL}' in the build"
    ]


def test_namespace_build_problems() -> None:
    objects = [
        {"kind": "Alert", "metadata": {"name": "a"}},
        {"kind": "Secret", "metadata": {"name": "s", "namespace": "org-acme"}},
        {"kind": "ConfigMap", "metadata": {"name": "c", "namespace": "org-other"}},
    ]
    assert namespace_build_problems(objects, "org-acme") == ["ConfigMap 'org-other/c'"]


def test_generated_resources(tmp_path: Path) -> None:
    # Flux's generated build: the YAML files, and below them each directory with a
    #  kustomization.yaml, built whole
    (tmp_path / "root.yaml").write_text("{}")
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "a.yaml").write_text("{}")
    (tmp_path / "built" / "inner").mkdir(parents=True)
    (tmp_path / "built" / "kustomization.yaml").write_text("{}")
    (tmp_path / "built" / "inner" / "b.yaml").write_text("{}")
    assert generated_resources(tmp_path) == [
        tmp_path / "root.yaml",
        tmp_path / "built",
        tmp_path / "plain" / "a.yaml",
    ]


@pytest.fixture(scope="module")
def root_build() -> list[dict]:
    return build(MC_DIR)


def test_root_build_applies_only_organizations_and_default(
    root_build: list[dict],
) -> None:
    # Flux dry-runs every object of a build before it applies any. An object in an organisation
    #  namespace fails that on a new management cluster, until organization-operator has created
    #  the namespace, and the Organization that makes it create one would never be applied.
    misplaced = misplaced_objects(root_build)
    assert not misplaced, (
        "The root Kustomization applies objects outside `default`; put them in the "
        f"organisation's namespace/ directory: {misplaced}"
    )


def test_root_build_applies_each_organisation_namespace(
    root_build: list[dict],
) -> None:
    problems = organization_namespace_problems(root_build)
    assert not problems, "\n".join(problems)


def test_organisation_namespace_builds_stay_in_the_namespace(
    root_build: list[dict],
) -> None:
    problems = [
        problem
        for k in root_build
        if (k.get("metadata", {}).get("labels") or {}).get(ORGANIZATION_NAMESPACE_LABEL)
        == "true"
        for problem in namespace_build_problems(
            build(REPO_DIR / k["spec"]["path"]), k["spec"]["targetNamespace"]
        )
    ]
    assert not problems, (
        "Objects in an organisation's namespace/ name another namespace: " f"{problems}"
    )
