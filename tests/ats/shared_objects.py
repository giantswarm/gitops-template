"""The shared-objects example: the ConfigMap `shared-ca-bundle` in bases/shared_objects, which
every organisation's directory lists with the organisation's namespace set there. Flux applies a
copy into each of those `org-*` namespaces and keeps every copy in sync with the base.

The check compares every copy with the base in Git, so an organisation that lists the base gets
it, and a change to the base reaches every copy. It then changes a copy and waits for Flux to put
it back. test_flux_objects.py runs it once the Kustomizations are ready.
"""

from pathlib import Path

import pykube
import pytest
import yaml
from flux_reconcile import request_reconcile, wait_until
from values_watch import owning_kustomization

REPO_DIR = Path(__file__).resolve().parents[2]
SOURCE_FILE = REPO_DIR / "bases" / "shared_objects" / "shared-ca-bundle.yaml"
ORGANIZATIONS_DIR = REPO_DIR / "management-clusters" / "MC_NAME" / "organizations"
# the directory in an organisation's directory that lists the base
COPY_DIR = "shared-objects"
CONFIG_MAP = "shared-ca-bundle"
# Flux applies the copies with the rest of the management cluster, and puts a changed copy back
#  at its next reconcile, which the check asks for
SYNC_TIMEOUT_SEC = 120
# the change to a copy, which Flux has to undo
CHANGED_DATA = "changed by the shared-objects check"


def source_config_map() -> dict:
    """The shared ConfigMap as it is in Git."""
    with SOURCE_FILE.open() as f:
        return yaml.safe_load(f)


def copy_namespaces(organisations_dir: Path) -> list[str]:
    """The namespaces of the copies: the one each organisation directory's COPY_DIR sets."""
    namespaces = []
    for kustomization_file in organisations_dir.glob(
        f"*/{COPY_DIR}/kustomization.yaml"
    ):
        with kustomization_file.open() as f:
            namespaces.append(yaml.safe_load(f)["namespace"])
    return sorted(namespaces)


def copy_problems(source: dict, copy: dict | None, namespace: str) -> list[str]:
    """Why `copy`, the ConfigMap in `namespace`, isn't a copy of `source`, if it isn't."""
    if copy is None:
        return [f"ConfigMap '{CONFIG_MAP}' isn't in namespace '{namespace}'"]
    if copy.get("data") != source.get("data"):
        return [f"ConfigMap '{namespace}/{CONFIG_MAP}' has other data than its source"]
    return []


def get_copy(api: pykube.HTTPClient, namespace: str) -> pykube.ConfigMap | None:
    return (
        pykube.ConfigMap.objects(api)
        .filter(namespace=namespace)
        .get_or_none(name=CONFIG_MAP)
    )


def wait_for_copies(
    api: pykube.HTTPClient, source: dict, namespaces: list[str], what: str
) -> None:
    """Wait until the ConfigMap in every one of `namespaces` has the source's data."""

    def problems() -> list[str]:
        found = []
        for namespace in namespaces:
            copy = get_copy(api, namespace)
            found += copy_problems(source, copy.obj if copy else None, namespace)
        return found

    wait_until(problems, SYNC_TIMEOUT_SEC, what)


def check_shared_object_copied(api: pykube.HTTPClient) -> None:
    """Check that every organisation that lists the base has a copy of it, then change one copy
    and wait for Flux to put it back."""
    source = source_config_map()
    namespaces = copy_namespaces(ORGANIZATIONS_DIR)
    if not namespaces:
        pytest.fail(
            f"No organisation in '{ORGANIZATIONS_DIR}' lists the shared object."
        )
    wait_for_copies(
        api, source, namespaces, "the organisations don't have the shared object"
    )

    copy = (
        pykube.ConfigMap.objects(api)
        .filter(namespace=namespaces[0])
        .get(name=CONFIG_MAP)
    )
    copy.patch({"data": dict.fromkeys(source["data"], CHANGED_DATA)})
    request_reconcile(owning_kustomization(api, copy.obj))
    wait_for_copies(
        api, source, namespaces[:1], "Flux didn't put the changed copy back"
    )
