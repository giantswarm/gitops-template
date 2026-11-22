"""Checks of the test's stand-in secret stores and the stores the examples read; they need no
cluster.

The store check reads the manifests under `management-clusters/` and `bases/`. It doesn't read the
snippets in the docs, such as the `ExternalSecret`s of docs/getting-started.md, which are shell
heredocs with variables in them.
"""

from pathlib import Path

import external_secrets
import pytest
import yaml
from fake_store import secret_stores, store_values
from kind_config import require_example
from store_refs import store_kinds
from workload_cluster_secrets import COMMON

REPO_DIR = Path(__file__).resolve().parents[2]
# the directories of manifests whose store references the check reads
MANIFEST_DIRS = ["management-clusters", "bases"]


def test_a_namespaced_store_in_each_namespace_that_reads_it() -> None:
    # customers can't create a ClusterSecretStore, only SecretStores in `default` and `org-*`
    stores = secret_stores(["default", "org-acme"])
    assert [
        (s["kind"], s["metadata"]["namespace"], s["metadata"]["name"]) for s in stores
    ] == [
        ("SecretStore", "default", "gitops-test"),
        ("SecretStore", "org-acme", "gitops-test"),
    ]
    assert stores[0]["spec"] == stores[1]["spec"]


def test_the_stand_in_store_holds_what_the_example_checks_read() -> None:
    require_example("workload-cluster-secrets")
    require_example("notifications")
    values = store_values()
    assert values["workload-clusters-common-token"] == COMMON.value
    assert {
        "gitops/hello-world-values",
        "gitops/github-commit-status-token",
        "gitops/github-webhook-token",
    } <= values.keys()


def repository_store_refs() -> list[tuple[str, str]]:
    """(file, kind of the store) of every store reference in MANIFEST_DIRS."""
    refs = []
    for directory in MANIFEST_DIRS:
        for path in sorted((REPO_DIR / directory).rglob("*.yaml")):
            with path.open() as f:
                for doc in yaml.safe_load_all(f):
                    if isinstance(doc, dict):
                        refs += [
                            (str(path.relative_to(REPO_DIR)), kind)
                            for kind in store_kinds(doc)
                        ]
    return refs


def test_examples_read_namespaced_stores() -> None:
    refs = repository_store_refs()
    if not refs:
        pytest.skip("Nothing in the repository reads a secret store.")
    assert [r for r in refs if r[1] != "SecretStore"] == []


def test_create_store_fails_at_once_without_its_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_secrets, "namespace_exists", lambda api, name: False)
    monkeypatch.setattr(
        external_secrets, "apply", lambda obj: pytest.fail("applied the store")
    )
    with pytest.raises(external_secrets.MissingNamespaceError) as e:
        store = secret_stores(["org-acme"])[0]
        external_secrets.create_store(None, store, 120)  # type: ignore[arg-type]
    assert "org-acme" in str(e.value)
