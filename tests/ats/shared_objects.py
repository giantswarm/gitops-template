"""The Kyverno policy `copy-shared-ca-bundle` copies a shared ConfigMap into every `org-*`
namespace and keeps the copies in sync with it.

The check creates a new organization namespace and waits for the copy, then changes the source
and waits for the copy to follow. test_flux_objects.py runs it once the Kustomizations are ready.
"""

import pykube
from flux_reconcile import suspend, wait_until
from values_watch import owning_kustomization

CONFIG_MAP = "shared-ca-bundle"
SOURCE_NAMESPACE = "default"
# a new organization namespace: the policy copies the ConfigMap when it's created
TEST_NAMESPACE = "org-shared-objects-test"
# Kyverno's background controller creates and updates the copies within seconds
SYNC_TIMEOUT_SEC = 60
# the change to the source: a key the copy has to get, and lose again
CHANGED_KEY = "sync-test"


def copy_problems(source: dict, copy: dict | None, namespace: str) -> list[str]:
    """Why `copy`, the ConfigMap in `namespace`, isn't a copy of `source`, if it isn't."""
    if copy is None:
        return [f"ConfigMap '{CONFIG_MAP}' isn't in namespace '{namespace}'"]
    if copy.get("data") != source.get("data"):
        return [f"ConfigMap '{namespace}/{CONFIG_MAP}' has other data than its source"]
    return []


def wait_for_copy(api: pykube.HTTPClient, source: pykube.ConfigMap, what: str) -> None:
    """Wait until the ConfigMap in TEST_NAMESPACE has the source's current data."""

    def problems() -> list[str]:
        source.reload()
        copy = (
            pykube.ConfigMap.objects(api)
            .filter(namespace=TEST_NAMESPACE)
            .get_or_none(name=CONFIG_MAP)
        )
        return copy_problems(source.obj, copy.obj if copy else None, TEST_NAMESPACE)

    wait_until(problems, SYNC_TIMEOUT_SEC, what)


def check_source_change_synced(
    api: pykube.HTTPClient, source: pykube.ConfigMap
) -> None:
    """Add CHANGED_KEY to the source and wait for the copy to get it, then take it out again."""
    # kustomize-controller would put the source back at its next apply
    kustomization = owning_kustomization(api, source.obj)
    suspend(kustomization)
    try:
        source.patch({"data": {CHANGED_KEY: "changed"}})
        try:
            wait_for_copy(api, source, "the change to the source wasn't copied")
        finally:
            # a merge patch: null deletes the key
            source.patch({"data": {CHANGED_KEY: None}})
        wait_for_copy(api, source, "the restored source wasn't copied")
    finally:
        kustomization.patch({"spec": {"suspend": False}})


def check_shared_object_copied(api: pykube.HTTPClient) -> None:
    """Create TEST_NAMESPACE, wait for the copy of the source in it, and check that a change to
    the source reaches the copy."""
    source = (
        pykube.ConfigMap.objects(api)
        .filter(namespace=SOURCE_NAMESPACE)
        .get(name=CONFIG_MAP)
    )
    namespace = pykube.Namespace(api, {"metadata": {"name": TEST_NAMESPACE}})
    namespace.create()
    try:
        wait_for_copy(
            api, source, "the ConfigMap wasn't copied into a new organization"
        )
        check_source_change_synced(api, source)
    finally:
        namespace.delete()
