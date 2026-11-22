"""The Kustomizations an organisation's namespace Kustomization applies, the workload clusters'
among them, run in the organisation's namespace: they have to name the repository's GitRepository
in `default`, follow the organisation's namespace Kustomization, and decrypt with a key Secret
that it applies too. Checks of root_build and of the repository's builds; they need no cluster,
only kubectl."""

import pytest
import yaml
from repository_gates import ORG_DIR, WORKLOAD_CLUSTERS_DIR
from root_build import (
    REPO_DIR,
    build,
    decryption_problems,
    namespace_builds,
    namespace_dependency_problems,
    source_problems,
)
from kind_config import RootKustomization, kind_test_config, require_example


def organization_kustomization() -> dict:
    """An organisation's namespace Kustomization, in `default`."""
    return {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": "mc-organization-acme", "namespace": "default"},
        "spec": {"targetNamespace": "org-acme"},
    }


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
    parent = organization_kustomization()
    parent["spec"]["sourceRef"] = REPOSITORY
    other = {"kind": "GitRepository", "name": "team", "namespace": "org-acme"}
    objects = [
        namespaced("wc", sourceRef={**REPOSITORY, "namespace": "default"}),
        namespaced("team", sourceRef=other),
    ]
    assert source_problems(objects, parent) == []


def test_source_problems_without_the_namespace() -> None:
    parent = organization_kustomization()
    parent["spec"]["sourceRef"] = REPOSITORY
    assert source_problems([namespaced("wc", sourceRef=REPOSITORY)], parent) == [
        "Kustomization 'wc' reads GitRepository 'your-repo' without "
        "`sourceRef.namespace: default`"
    ]


def test_namespace_dependency_problems_none() -> None:
    parent = organization_kustomization()
    objects = [
        namespaced(
            "wc", dependsOn=[{"name": "mc-organization-acme", "namespace": "default"}]
        ),
        # the apps follow the cluster, which follows the organisation's namespace
        namespaced("wc-apps", dependsOn=[{"name": "wc"}]),
    ]
    assert namespace_dependency_problems(objects, parent) == []


def test_namespace_dependency_problems() -> None:
    parent = organization_kustomization()
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


@pytest.fixture(
    scope="module",
    params=kind_test_config().roots(),
    ids=lambda r: r.management_cluster,
)
def root(request: pytest.FixtureRequest) -> list[dict]:
    """The build of each management cluster's root Kustomization."""
    root_kustomization: RootKustomization = request.param
    return build(REPO_DIR / root_kustomization.file.parent)


def test_organisation_namespace_kustomizations_read_the_repository_in_default(
    root: list[dict],
) -> None:
    # a Kustomization's sourceRef is in its own namespace unless it names one: the repository's
    #  GitRepository stays in `default`
    problems = [p for k, b in namespace_builds(root) for p in source_problems(b, k)]
    assert not problems, "\n".join(problems)


def test_organisation_namespace_kustomizations_follow_the_organisation(
    root: list[dict],
) -> None:
    # the organisation's namespace Kustomization applies every commit first, so the cluster
    #  Kustomizations it applies have their current spec, and its `organization`
    problems = [
        p
        for k, b in namespace_builds(root)
        for p in namespace_dependency_problems(b, k)
    ]
    assert not problems, "\n".join(problems)


def test_organisation_namespace_kustomizations_decrypt_with_their_keys(
    root: list[dict],
) -> None:
    # `decryption.secretRef` is in the Kustomization's own namespace: the cluster keys are in
    #  the organisation's namespace/secrets
    problems = [p for _, b in namespace_builds(root) for p in decryption_problems(b)]
    assert not problems, "\n".join(problems)


def _kinds_and_names(build_objects: list[dict]) -> set[tuple[str, str]]:
    return {(o["kind"], o["metadata"]["name"]) for o in build_objects}


def test_organisation_namespace_build_applies_the_cluster_kustomizations() -> None:
    require_example("organisation")
    # namespace/kustomization.yaml lists ../workload-clusters: the Kustomizations live next to
    #  the cluster directories they apply, and go into the organisation's namespace
    expected = set()
    for file in WORKLOAD_CLUSTERS_DIR.glob("*.yaml"):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                expected.add(("Kustomization", yaml.safe_load(f)["metadata"]["name"]))
    assert expected
    assert expected <= _kinds_and_names(build(ORG_DIR / "namespace"))


def test_organisation_namespace_build_applies_the_secret_stores() -> None:
    require_example("organisation")
    # namespace/kustomization.yaml lists ../multicluster/secret-stores, which has no Flux
    #  Kustomization of its own
    stores = build(ORG_DIR / "multicluster" / "secret-stores")
    assert stores
    assert _kinds_and_names(stores) <= _kinds_and_names(build(ORG_DIR / "namespace"))
