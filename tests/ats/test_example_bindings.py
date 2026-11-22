"""Checks of how the kind test binds its example checks to the examples, and of the data the
bindings hold; they need no cluster. Each builds a small repository of its own in `tmp_path`.
"""

from pathlib import Path

import kind_config
import pytest
from kind_config import (
    ConfigError,
    KindTestConfig,
    examples_required,
    kind_test_config,
)
from test_kind_config import write_root

ATS_DIR = Path(__file__).resolve().parent


def config(tmp_path: Path, settings: dict) -> KindTestConfig:
    return KindTestConfig(tmp_path, settings)


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
    with pytest.raises(ConfigError, match=r"'prune'.*paths"):
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


def test_a_broken_binding_fails_the_template_and_skips_in_a_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a binding whose path is gone drops its assertion files: in a fork that's an example it
    #  deleted, in the template it's a broken binding
    write_root(tmp_path, "golem")
    c = config(
        tmp_path,
        {
            "examples": {
                "hello-app": {
                    "paths": ["management-clusters/golem/HELLO_APP_RENAMED"],
                    "assertions": ["assertions/exists/hello-app"],
                }
            }
        },
    )
    monkeypatch.setattr(kind_config, "kind_test_config", lambda: c)
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/platform-gitops")
    assert list(kind_config.skipped_assertions()) == ["assertions/exists/hello-app"]
    assert kind_config.missing_examples() == []
    monkeypatch.setenv("GITHUB_REPOSITORY", "giantswarm/gitops-template")
    with pytest.raises(pytest.fail.Exception, match="hello-app"):
        kind_config.skipped_assertions()
    assert len(kind_config.missing_examples()) == 1


def test_the_template_binds_every_example_it_has() -> None:
    # In the template, every example check runs: a binding whose example can't be found is a
    #  broken binding, and an assertion file no binding names would be checked in a fork that
    #  deleted its example. A fork that deleted examples skips this; the template's CI fails.
    c = kind_test_config()
    missing = kind_config.missing_examples()
    assert not missing, "\n".join(missing)
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
