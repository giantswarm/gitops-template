"""Checks of what the kind test finds in a repository: its management clusters, their roots and
what each root reads; they need no cluster. Each builds a small repository of its own in
`tmp_path`."""

from pathlib import Path

import pytest
import yaml
from kind_config import (
    ConfigError,
    KindTestConfig,
    load_config,
    management_clusters,
    root_kustomization,
)

ATS_DIR = Path(__file__).resolve().parent


def write_root(
    repo: Path,
    mc: str,
    name: str = "",
    source: str = "gitops",
    decryption: str | None = "sops-gpg-master",
    path: str = "",
) -> Path:
    """`management-clusters/<mc>/<mc>.yaml`, as the basic tutorial writes it."""
    spec: dict = {
        "interval": "10m",
        "path": path or f"./management-clusters/{mc}",
        "prune": True,
        "serviceAccountName": "automation",
        "sourceRef": {"kind": "GitRepository", "name": source},
    }
    if decryption:
        spec["decryption"] = {"provider": "sops", "secretRef": {"name": decryption}}
    file = repo / "management-clusters" / mc / f"{mc}.yaml"
    file.parent.mkdir(parents=True)
    file.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
                "kind": "Kustomization",
                "metadata": {"name": name or f"{mc}-gitops", "namespace": "default"},
                "spec": spec,
            }
        )
    )
    return file


def test_every_directory_with_its_root_is_a_management_cluster(tmp_path: Path) -> None:
    write_root(tmp_path, "MC_NAME")
    write_root(tmp_path, "golem")
    # a directory without <name>/<name>.yaml is no management cluster
    (tmp_path / "management-clusters" / "notes").mkdir()
    assert management_clusters(tmp_path, None) == ["MC_NAME", "golem"]


def test_configured_management_clusters_win(tmp_path: Path) -> None:
    write_root(tmp_path, "MC_NAME")
    write_root(tmp_path, "golem")
    assert management_clusters(tmp_path, ["golem"]) == ["golem"]


def test_a_configured_management_cluster_has_to_exist(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    with pytest.raises(ConfigError, match=r"'gazelle'.*management-clusters/gazelle"):
        management_clusters(tmp_path, ["gazelle"])


def test_no_management_cluster_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "management-clusters").mkdir()
    with pytest.raises(ConfigError, match="No management cluster"):
        management_clusters(tmp_path, None)


def test_root_kustomization_names_its_source_and_key(tmp_path: Path) -> None:
    write_root(tmp_path, "golem", source="platform-gitops", decryption="golem-master")
    root = root_kustomization(tmp_path, "golem")
    assert root.name == "golem-gitops"
    assert root.namespace == "default"
    assert root.git_repository == ("default", "platform-gitops")
    assert root.decryption_secret == ("default", "golem-master")
    assert root.file == Path("management-clusters/golem/golem.yaml")


def test_root_kustomization_without_decryption(tmp_path: Path) -> None:
    # ESO only: the tutorial leaves `decryption` out
    write_root(tmp_path, "golem", decryption=None)
    assert root_kustomization(tmp_path, "golem").decryption_secret is None


def test_root_kustomization_source_in_another_namespace(tmp_path: Path) -> None:
    file = write_root(tmp_path, "golem")
    doc = yaml.safe_load(file.read_text())
    doc["spec"]["sourceRef"]["namespace"] = "flux-giantswarm"
    file.write_text(yaml.safe_dump(doc))
    assert root_kustomization(tmp_path, "golem").git_repository == (
        "flux-giantswarm",
        "gitops",
    )


def test_root_kustomization_has_to_apply_its_directory(tmp_path: Path) -> None:
    write_root(tmp_path, "golem", path="./management-clusters/other")
    with pytest.raises(ConfigError, match="no Flux Kustomization that applies"):
        root_kustomization(tmp_path, "golem")


def test_a_root_reading_no_git_repository_has_none(tmp_path: Path) -> None:
    file = write_root(tmp_path, "golem")
    doc = yaml.safe_load(file.read_text())
    doc["spec"]["sourceRef"] = {"kind": "OCIRepository", "name": "artifact"}
    file.write_text(yaml.safe_dump(doc))
    assert root_kustomization(tmp_path, "golem").git_repository is None


def test_load_config_without_a_file(tmp_path: Path) -> None:
    assert load_config(tmp_path / "kind-test.yaml") == {}


def test_load_config_refuses_unknown_keys(tmp_path: Path) -> None:
    file = tmp_path / "kind-test.yaml"
    file.write_text("managementCluster: [golem]\n")
    with pytest.raises(ConfigError, match="managementCluster"):
        load_config(file)


def config(tmp_path: Path, settings: dict) -> KindTestConfig:
    return KindTestConfig(tmp_path, settings)


def test_the_git_repositories_and_keys_of_every_root(tmp_path: Path) -> None:
    write_root(tmp_path, "golem", source="gitops", decryption="sops-gpg-master")
    write_root(tmp_path, "gazelle", source="gitops", decryption=None)
    write_root(tmp_path, "grizzly", source="other", decryption="grizzly-master")
    c = config(tmp_path, {})
    assert c.git_repositories() == [("default", "gitops"), ("default", "other")]
    assert c.decryption_secrets() == [
        ("default", "grizzly-master"),
        ("default", "sops-gpg-master"),
    ]
