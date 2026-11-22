"""A management cluster's root Kustomization has to apply on a new management cluster, where no
organisation namespace exists yet. Checks of root_build and of the root build of every management
cluster the kind test applies; they need no cluster, only kubectl."""

from pathlib import Path

import pytest
from kind_config import RootKustomization, kind_test_config, require_example
from root_build import (
    ORGANIZATION_NAMESPACE_LABEL,
    REPO_DIR,
    build,
    generated_resources,
    misplaced_objects,
    namespace_build_problems,
    namespace_builds,
    organization_namespace_problems,
    root_dependency_problems,
    unguarded_kustomizations,
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


def test_organization_namespace_problems_before_the_first_organisation() -> None:
    # step 1 of the basic tutorial: the management cluster has no organisation yet
    assert organization_namespace_problems([]) == []


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


def test_root_dependency_problems_of_another_kustomization() -> None:
    # every Kustomization the root applies follows it, not only the organisations' namespace
    #  ones; the root itself is in its own build and depends on nothing
    root = kustomization("mc-gitops")
    apps = kustomization("mc-multicluster-apps-acme")
    assert root_dependency_problems([root, apps], "mc-gitops") == [
        "Kustomization 'default/mc-multicluster-apps-acme' doesn't depend on 'mc-gitops'"
    ]


def test_unguarded_kustomizations() -> None:
    guarded = kustomization("mc-gitops")
    guarded["metadata"]["annotations"] = {
        "kustomize.toolkit.fluxcd.io/prune": "disabled"
    }
    unguarded = organization_kustomization("org-acme")
    assert unguarded_kustomizations([ORGANIZATION, guarded, unguarded]) == [
        "Kustomization 'default/mc-organization-acme'"
    ]


def test_root_dependency_problems_in_another_namespace() -> None:
    k = organization_kustomization("org-acme")
    k["spec"]["dependsOn"] = [{"name": "mc-gitops", "namespace": "flux-giantswarm"}]
    assert root_dependency_problems([k], "mc-gitops") == [
        "Kustomization 'default/mc-organization-acme' doesn't depend on 'mc-gitops'"
    ]


def test_root_kustomization_name() -> None:
    require_example("management-cluster")
    assert kind_test_config().root("MC_NAME").name == "mc-name-gitops"


@pytest.fixture(
    scope="module",
    params=kind_test_config().roots(),
    ids=lambda r: r.management_cluster,
)
def root(request: pytest.FixtureRequest) -> RootKustomization:
    return request.param


@pytest.fixture(scope="module")
def root_build(root: RootKustomization) -> list[dict]:
    return build(REPO_DIR / root.file.parent)


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


def test_root_build_kustomizations_follow_the_root(
    root: RootKustomization, root_build: list[dict]
) -> None:
    # the root applies every commit first, so an object that moves between the root and an
    #  organisation's namespace/ moves in that order
    problems = root_dependency_problems(root_build, root.name)
    assert not problems, "\n".join(problems)


def test_root_build_guards_its_kustomizations(root_build: list[dict]) -> None:
    # A Kustomization that leaves the root's build, renamed or deleted, would be deleted, and
    #  its finalizer would delete everything it applied, every app of an organisation's clusters
    #  among it. The annotation leaves it, the root itself included, as the root applies itself.
    unguarded = unguarded_kustomizations(root_build)
    assert not unguarded, (
        "Give these Kustomizations the `kustomize.toolkit.fluxcd.io/prune: disabled` "
        f"annotation, see docs/explanation/deletion-protection.md: {unguarded}"
    )


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
