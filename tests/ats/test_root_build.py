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
    decryption_problems,
    generated_resources,
    misplaced_objects,
    namespace_build_problems,
    namespace_dependency_problems,
    organization_namespace_problems,
    root_dependency_problems,
    root_kustomization_name,
    source_problems,
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


def test_root_dependency_problems_none() -> None:
    k = organization_kustomization("org-acme")
    k["spec"]["dependsOn"] = [{"name": "mc-gitops"}]
    assert root_dependency_problems([k], "mc-gitops") == []


def test_root_dependency_problems_without_the_root() -> None:
    k = organization_kustomization("org-acme")
    k["spec"]["dependsOn"] = [{"name": "other"}]
    assert root_dependency_problems([ORGANIZATION, k], "mc-gitops") == [
        "Kustomization 'default/mc-organization-acme' doesn't depend on 'mc-gitops'"
    ]
    del k["spec"]["dependsOn"]
    assert root_dependency_problems([k], "mc-gitops") == [
        "Kustomization 'default/mc-organization-acme' doesn't depend on 'mc-gitops'"
    ]


def test_root_dependency_problems_in_another_namespace() -> None:
    k = organization_kustomization("org-acme")
    k["spec"]["dependsOn"] = [{"name": "mc-gitops", "namespace": "flux-system"}]
    assert root_dependency_problems([k], "mc-gitops") == [
        "Kustomization 'default/mc-organization-acme' doesn't depend on 'mc-gitops'"
    ]


def namespaced(name: str, **spec: object) -> dict:
    """A Kustomization of an organisation's namespace/ build, which names no namespace."""
    return {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": name},
        "spec": spec,
    }


REPOSITORY = {"kind": "GitRepository", "name": "your-repo"}


def test_source_problems_none() -> None:
    parent = organization_kustomization("org-acme")
    parent["spec"]["sourceRef"] = REPOSITORY
    other = {"kind": "GitRepository", "name": "team", "namespace": "org-acme"}
    objects = [
        namespaced("wc", sourceRef={**REPOSITORY, "namespace": "default"}),
        namespaced("team", sourceRef=other),
    ]
    assert source_problems(objects, parent) == []


def test_source_problems_without_the_namespace() -> None:
    parent = organization_kustomization("org-acme")
    parent["spec"]["sourceRef"] = REPOSITORY
    assert source_problems([namespaced("wc", sourceRef=REPOSITORY)], parent) == [
        "Kustomization 'wc' reads GitRepository 'your-repo' without "
        "`sourceRef.namespace: default`"
    ]


def test_namespace_dependency_problems_none() -> None:
    parent = organization_kustomization("org-acme")
    objects = [
        namespaced(
            "wc", dependsOn=[{"name": "mc-organization-acme", "namespace": "default"}]
        ),
        # the apps follow the cluster, which follows the organisation's namespace
        namespaced("wc-apps", dependsOn=[{"name": "wc"}]),
    ]
    assert namespace_dependency_problems(objects, parent) == []


def test_namespace_dependency_problems() -> None:
    parent = organization_kustomization("org-acme")
    objects = [
        namespaced("wc"),
        namespaced("other", dependsOn=[{"name": "mc-organization-acme"}]),
        namespaced("wc-apps", dependsOn=[{"name": "missing"}]),
    ]
    assert namespace_dependency_problems(objects, parent) == [
        "Kustomization 'wc' doesn't depend on 'default/mc-organization-acme'",
        "Kustomization 'other' doesn't depend on 'default/mc-organization-acme'",
        "Kustomization 'wc-apps' doesn't depend on 'default/mc-organization-acme'",
    ]


def test_decryption_problems() -> None:
    key = {"kind": "Secret", "metadata": {"name": "sops-age-wc"}}
    objects = [
        key,
        namespaced("wc", decryption={"secretRef": {"name": "sops-age-wc"}}),
        namespaced("other", decryption={"secretRef": {"name": "sops-gpg-master"}}),
        namespaced("plain"),
    ]
    assert decryption_problems(objects) == [
        "Kustomization 'other' decrypts with Secret 'sops-gpg-master', which isn't in "
        "its build"
    ]


def test_root_kustomization_name() -> None:
    assert root_kustomization_name() == "mc-name-gitops"


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


def test_organisation_namespace_kustomizations_follow_the_root(
    root_build: list[dict],
) -> None:
    # the root applies every commit first, so an object that moves between the root and an
    #  organisation's namespace/ moves in that order
    problems = root_dependency_problems(root_build, root_kustomization_name())
    assert not problems, "\n".join(problems)


def namespace_builds(root_build: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Each organisation's namespace Kustomization in `root_build`, with its build."""
    return [
        (k, build(REPO_DIR / k["spec"]["path"]))
        for k in root_build
        if (k.get("metadata", {}).get("labels") or {}).get(ORGANIZATION_NAMESPACE_LABEL)
        == "true"
    ]


def test_organisation_namespace_builds_stay_in_the_namespace(
    root_build: list[dict],
) -> None:
    problems = [
        problem
        for k, b in namespace_builds(root_build)
        for problem in namespace_build_problems(b, k["spec"]["targetNamespace"])
    ]
    assert not problems, (
        "Objects in an organisation's namespace/ name another namespace: " f"{problems}"
    )


def test_organisation_namespace_kustomizations_read_the_repository_in_default(
    root_build: list[dict],
) -> None:
    # a Kustomization's sourceRef is in its own namespace unless it names one: the repository's
    #  GitRepository stays in `default`
    problems = [
        p for k, b in namespace_builds(root_build) for p in source_problems(b, k)
    ]
    assert not problems, "\n".join(problems)


def test_organisation_namespace_kustomizations_follow_the_organisation(
    root_build: list[dict],
) -> None:
    # the organisation's namespace Kustomization applies every commit first, so the cluster
    #  Kustomizations it applies have their current spec, and its `organization`
    problems = [
        p
        for k, b in namespace_builds(root_build)
        for p in namespace_dependency_problems(b, k)
    ]
    assert not problems, "\n".join(problems)


def test_organisation_namespace_kustomizations_decrypt_with_their_keys(
    root_build: list[dict],
) -> None:
    # `decryption.secretRef` is in the Kustomization's own namespace: the cluster keys are in
    #  the organisation's namespace/secrets
    problems = [
        p for _, b in namespace_builds(root_build) for p in decryption_problems(b)
    ]
    assert not problems, "\n".join(problems)
