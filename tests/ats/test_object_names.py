"""Checks that the API server takes the name of every object in the examples; needs no cluster."""

from pathlib import Path

import pytest
from object_names import invalid_names, invalid_names_in, is_valid

REPOSITORY = Path(__file__).resolve().parent / "../.."


@pytest.mark.parametrize(
    "name",
    [
        "hello-world",
        "a.b-c.1",
        "${cluster_name}-hello-world",
        "<< inputs.cluster >>-hello-world",
    ],
)
def test_valid_names(name: str) -> None:
    assert is_valid(name)


@pytest.mark.parametrize(
    "name",
    [
        "secret-to-be-created-directly-in-WC",
        "under_score",
        "-leading-hyphen",
        "trailing-hyphen-",
        "",
        "a" * 254,
    ],
)
def test_invalid_names(name: str) -> None:
    assert not is_valid(name)


def test_invalid_names_in_a_manifest() -> None:
    manifest = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: In-Capitals
---
# a kustomization.yaml names nothing
kind: Kustomization
resources: [a.yaml]
---
# a JSON patch isn't an object
- op: add
  path: /metadata/name
  value: In-Capitals
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: system:In-Capitals
---
apiVersion: v1
kind: Secret
metadata:
  name: ${cluster_name}-fine
"""
    assert invalid_names_in(manifest) == ["ConfigMap/In-Capitals"]


def test_names_a_resource_set_renders() -> None:
    manifest = """
apiVersion: fluxcd.controlplane.io/v1
kind: ResourceSet
metadata:
  name: fine
spec:
  resources:
    - kind: HelmRelease
      metadata:
        name: << inputs.cluster >>-Hello
    - kind: OCIRepository
      metadata:
        name: << inputs.cluster >>-hello
"""
    assert invalid_names_in(manifest) == ["HelmRelease/<< inputs.cluster >>-Hello"]


@pytest.mark.parametrize("kind", ["Namespace", "Service"])
def test_names_that_are_dns_labels(kind: str) -> None:
    # a label has no dots and at most 63 characters
    for name in ["a.b", "a" * 64]:
        manifest = f"kind: {kind}\nmetadata:\n  name: {name}\n"
        assert invalid_names_in(manifest) == [f"{kind}/{name}"]
    assert invalid_names_in(f"kind: {kind}\nmetadata:\n  name: {'a' * 63}\n") == []


def test_invalid_names_below_a_directory(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a/bad.yaml").write_text("kind: ConfigMap\nmetadata:\n  name: Bad\n")
    (tmp_path / "good.yaml").write_text("kind: ConfigMap\nmetadata:\n  name: good\n")
    assert invalid_names(tmp_path) == ["a/bad.yaml: ConfigMap/Bad"]


@pytest.mark.parametrize("directory", ["bases", "management-clusters"])
def test_example_object_names(directory: str) -> None:
    assert invalid_names(REPOSITORY / directory) == []
