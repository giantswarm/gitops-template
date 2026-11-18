"""HelmReleases, ConfigMaps and lookups for the tests of helm_values and values_sources."""

from checks.helm_release_sources import Lookup

NAMESPACE = "org-org-name"


def config_map(values: str, key: str = "values") -> dict:
    """A ConfigMap with `values` under `key`."""
    return {"data": {key: values}}


def lookup_for(objects: dict[tuple[str, str], dict]) -> Lookup:
    """A lookup of `objects` by (kind, name), in NAMESPACE only."""

    def lookup(kind: str, namespace: str, name: str) -> dict | None:
        return objects.get((kind, name)) if namespace == NAMESPACE else None

    return lookup


def helm_release(*entries: dict, values: dict | None = None) -> dict:
    """A HelmRelease in NAMESPACE with the `valuesFrom` entries and `spec.values`."""
    spec = {"valuesFrom": list(entries), "values": values}
    return {"metadata": {"name": "hr", "namespace": NAMESPACE}, "spec": spec}


def ref(name: str, kind: str = "ConfigMap", **extra: object) -> dict:
    """A `valuesFrom` entry that reads the key `values`."""
    return {"kind": kind, "name": name, "valuesKey": "values", **extra}


# the stage's node pool and a region's extra one, as the examples set them
STAGE = config_map("global:\n  nodePools:\n    nodepool0:\n      minSize: 10\n")
REGION = config_map("global:\n  nodePools:\n    large:\n      minSize: 1\n")
