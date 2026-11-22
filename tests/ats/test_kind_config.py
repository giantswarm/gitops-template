"""Checks of what the kind test finds in a repository and how it binds its example checks; they
need no cluster. Each builds a small repository of its own in `tmp_path`."""

from pathlib import Path

import kind_config
import pytest
import yaml
from kind_config import (
    ConfigError,
    KindTestConfig,
    examples_required,
    kind_test_config,
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
    with pytest.raises(ConfigError, match="'gazelle'.*management-clusters/gazelle"):
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


def test_an_example_that_is_there_runs(tmp_path: Path) -> None:
    write_root(tmp_path, "MC_NAME")
    (tmp_path / "management-clusters/MC_NAME/organizations/ORG_NAME").mkdir(
        parents=True
    )
    c = config(
        tmp_path,
        {
            "examples": {
                "organisation": {
                    "paths": ["management-clusters/MC_NAME/organizations/ORG_NAME"]
                }
            }
        },
    )
    assert c.example_skip_reason("organisation") is None


def test_an_example_that_is_gone_is_skipped(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    c = config(
        tmp_path,
        {
            "examples": {
                "organisation": {
                    "paths": ["management-clusters/MC_NAME/organizations/ORG_NAME"]
                }
            }
        },
    )
    reason = c.example_skip_reason("organisation")
    assert reason is not None
    assert "example 'organisation'" in reason
    assert "management-clusters/MC_NAME/organizations/ORG_NAME" in reason
    assert "isn't in the repository" in reason


def test_an_example_of_a_management_cluster_the_test_leaves_out_is_skipped(
    tmp_path: Path,
) -> None:
    write_root(tmp_path, "MC_NAME")
    write_root(tmp_path, "golem")
    c = config(
        tmp_path,
        {
            "managementClusters": ["golem"],
            "examples": {"notifications": {"paths": ["management-clusters/MC_NAME"]}},
        },
    )
    reason = c.example_skip_reason("notifications")
    assert reason is not None
    assert "management cluster 'MC_NAME', which the test doesn't apply" in reason


def test_an_example_without_a_binding_is_skipped(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    reason = config(tmp_path, {}).example_skip_reason("prune")
    assert reason is not None
    assert "no binding for the example 'prune'" in reason


def test_a_binding_needs_its_paths(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    with pytest.raises(ConfigError, match="'prune'.*paths"):
        config(tmp_path, {"examples": {"prune": {}}})


def test_assertion_directories_of_a_skipped_example_are_left_out(
    tmp_path: Path,
) -> None:
    write_root(tmp_path, "golem")
    (tmp_path / "management-clusters/golem/apps").mkdir()
    c = config(
        tmp_path,
        {
            "examples": {
                "gone": {
                    "paths": ["management-clusters/MC_NAME"],
                    "assertions": ["assertions/exists/gone"],
                },
                "there": {
                    "paths": ["management-clusters/golem/apps"],
                    "assertions": ["assertions/exists/there"],
                },
            }
        },
    )
    assert c.skipped_assertion_dirs() == {
        "assertions/exists/gone": c.example_skip_reason("gone")
    }


def test_node_pools_by_namespace(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    c = config(
        tmp_path,
        {"nodePools": {"org-acme": {"prod": ["nodepool0", "large"], "dev": []}}},
    )
    assert c.node_pools() == {
        "org-acme": {"org-acme/prod": {"nodepool0", "large"}, "org-acme/dev": set()}
    }


def test_cluster_base_apps(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    c = config(tmp_path, {"clusterBaseApps": {"org-acme/prod": ["prod-ingress"]}})
    assert c.cluster_base_apps() == {"org-acme/prod": ["prod-ingress"]}


def test_secret_store_stand_in(tmp_path: Path) -> None:
    write_root(tmp_path, "golem")
    data = [{"key": "gitops/a", "value": "b"}]
    c = config(tmp_path, {"secretStore": {"name": "test-store", "data": data}})
    assert c.secret_store() == ("test-store", data)
    assert config(tmp_path, {}).secret_store() is None


def test_examples_are_required_in_the_template_only() -> None:
    assert examples_required({"GITHUB_REPOSITORY": "giantswarm/gitops-template"})
    assert not examples_required({"GITHUB_REPOSITORY": "acme/platform-gitops"})
    assert not examples_required({})


def test_a_missing_example_fails_the_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_root(tmp_path, "golem")
    c = config(
        tmp_path, {"examples": {"prune": {"paths": ["management-clusters/MC_NAME"]}}}
    )
    monkeypatch.setattr(kind_config, "kind_test_config", lambda: c)
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/platform-gitops")
    with pytest.raises(pytest.skip.Exception, match="isn't in this repository"):
        kind_config.require_example("prune")
    monkeypatch.setenv("GITHUB_REPOSITORY", "giantswarm/gitops-template")
    with pytest.raises(pytest.fail.Exception, match="The template's own CI"):
        kind_config.require_example("prune")


def test_the_template_binds_every_example_it_has() -> None:
    # In the template, every example check runs: a binding whose example can't be found is a
    #  broken binding, and an assertion file no binding names would be checked in a fork that
    #  deleted its example. A fork that deleted examples skips this.
    c = kind_test_config()
    if any(c.example_skip_reason(name) for name in c.examples):
        pytest.skip("The repository doesn't have all of the template's examples.")
    bound = [
        Path(a)
        for binding in c.examples.values()
        for a in binding.get("assertions") or []
    ]
    for path in bound:
        assert (ATS_DIR / path).exists(), f"{path} is bound but isn't there"
    unbound = [
        str(f.relative_to(ATS_DIR))
        for f in sorted((ATS_DIR / "assertions").rglob("*.yaml"))
        if not any(
            b == f.relative_to(ATS_DIR) or b in f.relative_to(ATS_DIR).parents
            for b in bound
        )
    ]
    assert not unbound, f"Assertion files no example in kind-test.yaml names: {unbound}"
