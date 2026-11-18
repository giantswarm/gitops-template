"""The values helm-controller gives the chart of a HelmRelease.

It follows helm-controller (`ChartValuesFromReferences` and `MergeMaps` in fluxcd/pkg chartutil):
every `valuesFrom` entry is read in order from the HelmRelease's namespace and merged into the
values so far, then `spec.values` is merged last. Maps are merged; anything else replaces what
was there. An optional entry whose object or key is missing is skipped.
"""

import base64
import binascii
from typing import Any

import yaml
from checks.helm_release_sources import Lookup

VALUES_KINDS = ("ConfigMap", "Secret")
DEFAULT_VALUES_KEY = "values.yaml"


class ValuesSourceError(Exception):
    """A `valuesFrom` entry that helm-controller would fail on, or that this module can't read."""

    def __init__(self, entry: dict, namespace: str, problem: str) -> None:
        super().__init__(
            f"valuesFrom {entry.get('kind')} '{namespace}/{entry.get('name')}': {problem}"
        )


def merge_maps(a: dict, b: dict) -> dict:
    """`b` merged into `a`: maps are merged, anything else in `b` replaces what is in `a`."""
    out = dict(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_maps(out[key], value)
        else:
            out[key] = value
    return out


def values_text(entry: dict, obj: dict | None) -> str | None:
    """The text under the entry's key in `obj`, or None if there is no object or no key."""
    data = (obj or {}).get("data") or {}
    key = entry.get("valuesKey", DEFAULT_VALUES_KEY)
    if key not in data:
        return None
    if entry["kind"] == "Secret":
        return base64.b64decode(data[key]).decode()
    return data[key]


def values_from_entry(entry: dict, namespace: str, lookup: Lookup) -> dict:
    """The values of one `valuesFrom` entry of a HelmRelease in `namespace`."""
    if entry.get("kind") not in VALUES_KINDS:
        raise ValuesSourceError(
            entry, namespace, "only ConfigMaps and Secrets hold values"
        )
    if not entry.get("name"):
        raise ValuesSourceError(entry, namespace, "the entry has no name")
    if entry.get("targetPath"):
        # helm-controller sets the text at that path with Helm's --set syntax; nothing here
        #  uses it, so it isn't modelled.
        raise ValuesSourceError(
            entry, namespace, "targetPath isn't supported by this test"
        )
    text = read_values_text(entry, namespace, lookup)
    if text is None:
        if entry.get("optional"):
            return {}
        key = entry.get("valuesKey", DEFAULT_VALUES_KEY)
        raise ValuesSourceError(
            entry, namespace, f"the object or its key '{key}' is missing"
        )
    return parse_values(entry, namespace, text)


def read_values_text(entry: dict, namespace: str, lookup: Lookup) -> str | None:
    """The entry's text, as values_text reads it, with decoding errors as ValuesSourceError."""
    try:
        return values_text(entry, lookup(entry["kind"], namespace, entry["name"]))
    except (binascii.Error, UnicodeDecodeError) as e:
        raise ValuesSourceError(
            entry, namespace, f"the values can't be decoded: {e}"
        ) from e


def parse_values(entry: dict, namespace: str, text: str) -> dict:
    """The values map in the entry's `text`."""
    try:
        values = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValuesSourceError(
            entry, namespace, f"the values aren't valid YAML: {e}"
        ) from e
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValuesSourceError(entry, namespace, "the values aren't a map")
    return values


def merged_values(hr: dict, lookup: Lookup) -> dict:
    """The values helm-controller gives the chart of `hr`."""
    namespace = hr["metadata"]["namespace"]
    values: dict[str, Any] = {}
    for entry in hr["spec"].get("valuesFrom") or []:
        values = merge_maps(values, values_from_entry(entry, namespace, lookup))
    return merge_maps(values, hr["spec"].get("values") or {})
