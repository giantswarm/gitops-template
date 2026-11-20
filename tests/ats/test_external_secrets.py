"""Checks of the test's stand-in secret stores and the stores the examples read; they need no
cluster."""

from pathlib import Path

import yaml
from external_secrets import STORE_NAME, secret_stores

REPO_DIR = Path(__file__).resolve().parents[2]


def test_a_namespaced_store_in_each_namespace_that_reads_it() -> None:
    # customers can't create a ClusterSecretStore, only SecretStores in `default` and `org-*`
    stores = secret_stores()
    assert [
        (s["kind"], s["metadata"]["namespace"], s["metadata"]["name"]) for s in stores
    ] == [
        ("SecretStore", "default", STORE_NAME),
        ("SecretStore", "org-org-name", STORE_NAME),
    ]
    assert stores[0]["spec"] == stores[1]["spec"]


def store_refs() -> list[tuple[str, str]]:
    """(file, kind of the store) of every ExternalSecret in the examples that reads a store,
    rather than only a generator."""
    refs = []
    for path in sorted((REPO_DIR / "management-clusters").rglob("*.yaml")):
        with path.open() as f:
            for doc in yaml.safe_load_all(f):
                if not isinstance(doc, dict) or doc.get("kind") != "ExternalSecret":
                    continue
                store_ref = doc["spec"].get("secretStoreRef")
                if store_ref:
                    refs.append((str(path.relative_to(REPO_DIR)), store_ref["kind"]))
    return refs


def test_examples_read_namespaced_stores() -> None:
    refs = store_refs()
    assert refs
    assert [r for r in refs if r[1] != "SecretStore"] == []
