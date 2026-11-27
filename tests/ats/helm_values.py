"""The values helm-controller gives the chart of a HelmRelease.

It follows helm-controller (`ChartValuesFromReferences` and `MergeMaps` in fluxcd/pkg chartutil):
every `valuesFrom` entry is read in order from the HelmRelease's namespace and merged into the
values so far, then `spec.values` is merged last. Maps are merged; anything else replaces what
was there. An optional entry whose object or key is missing is skipped.
"""

from typing import Any

from checks.helm_release_sources import Lookup
from values_sources import values_from_entry


def merge_maps(a: dict, b: dict) -> dict:
    """`b` merged into `a`: maps are merged, anything else in `b` replaces what is in `a`."""
    out = dict(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_maps(out[key], value)
        else:
            out[key] = value
    return out


def merged_values(hr: dict, lookup: Lookup) -> dict:
    """The values helm-controller gives the chart of `hr`."""
    namespace = hr["metadata"]["namespace"]
    values: dict[str, Any] = {}
    for entry in hr["spec"].get("valuesFrom") or []:
        values = merge_maps(values, values_from_entry(entry, namespace, lookup))
    return merge_maps(values, hr["spec"].get("values") or {})
