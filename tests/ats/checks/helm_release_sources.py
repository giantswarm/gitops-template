"""What a HelmRelease takes its chart and its kubeconfig from, and looking it up."""

from collections.abc import Callable

import pykube

from checks.kinds import REFERENCED_KINDS

# (kind, namespace, name) -> the object, or None if it doesn't exist
Lookup = Callable[[str, str, str], dict | None]


def cluster_lookup(api: pykube.HTTPClient) -> Lookup:
    """Get objects from the cluster, each one once."""
    found: dict[tuple[str, str, str], dict | None] = {}

    def lookup(kind: str, namespace: str, name: str) -> dict | None:
        if (kind, namespace, name) not in found:
            obj = (
                REFERENCED_KINDS[kind]
                .objects(api)
                .filter(namespace=namespace)
                .get_or_none(name=name)
            )
            found[(kind, namespace, name)] = obj.obj if obj else None
        return found[(kind, namespace, name)]

    return lookup


def chart_source(hr: dict) -> tuple[str, str, str] | None:
    """`(kind, namespace, name)` of the `chartRef`, or else the `chart.spec.sourceRef`."""
    spec = hr["spec"]
    ref = spec.get("chartRef") or ((spec.get("chart") or {}).get("spec") or {}).get(
        "sourceRef"
    )
    if not ref:
        return None
    return (
        ref.get("kind", ""),
        ref.get("namespace", hr["metadata"]["namespace"]),
        ref.get("name", ""),
    )


def chart_source_key(hr: dict) -> str | None:
    source = chart_source(hr)
    return f"{source[1]}/{source[2]}" if source else None


def chart_name(hr: dict, lookup: Lookup) -> str | None:
    """The name of the chart the HelmRelease installs, if the test can tell.

    `chart.spec.chart` names it. For a `chartRef`, the OCIRepository's URL or the HelmChart's
    `chart` does.
    """
    chart = ((hr["spec"].get("chart") or {}).get("spec") or {}).get("chart")
    if chart:
        return chart.rstrip("/").rsplit("/", 1)[-1]
    source = chart_source(hr)
    if source is None or source[0] not in ("OCIRepository", "HelmChart"):
        return None
    obj = lookup(*source)
    if obj is None:
        return None
    field = "url" if source[0] == "OCIRepository" else "chart"
    return obj["spec"].get(field, "").rstrip("/").rsplit("/", 1)[-1] or None


def kubeconfig_secret(hr: dict) -> str | None:
    return ((hr["spec"].get("kubeConfig") or {}).get("secretRef") or {}).get("name")
