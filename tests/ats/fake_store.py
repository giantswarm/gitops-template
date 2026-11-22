"""The test's stand-in for the secret manager: a SecretStore with the fake provider, which keeps
its values in the store itself. `secretStore` in kind-test.yaml names it and holds its values;
without it, the test creates no store.

external_secrets.py creates the store in `default`, organization_operator in every organisation's
namespace. For the template, the store is the one the examples' ExternalSecrets read, and
docs/how-to/external-secrets.md, "A secret store for testing", has a store of the same name for
trying the guides by hand.
"""

from collections.abc import Iterable

from kind_config import kind_test_config

DEFAULT_STORE_NAMESPACE = "default"


def store_values() -> dict[str, str]:
    """The stand-in store's values, by key."""
    store = kind_test_config().secret_store()
    return {item["key"]: item["value"] for item in store[1]} if store else {}


def secret_stores(namespaces: Iterable[str]) -> list[dict]:
    """The stand-in store in each of `namespaces`, or none without one."""
    store = kind_test_config().secret_store()
    if store is None:
        return []
    name, data = store
    return [
        {
            "apiVersion": "external-secrets.io/v1",
            "kind": "SecretStore",
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"provider": {"fake": {"data": data}}},
        }
        for namespace in namespaces
    ]
