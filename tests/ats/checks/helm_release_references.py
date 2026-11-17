"""R1-R4: what a HelmRelease refers to has to exist."""

from collections.abc import Collection

from checks.helm_release_classes import depends_on_keys
from checks.helm_release_sources import (
    Lookup,
    chart_source,
    chart_source_key,
    kubeconfig_secret,
)
from checks.kinds import CHART_SOURCE_KINDS


def management_cluster_objects(hr: dict) -> set[str]:
    """R3: `<cluster>-kubeconfig` and `<cluster>-cluster-values`, for a kubeconfig Secret
    named `<cluster>-kubeconfig`. The management cluster creates both."""
    secret = kubeconfig_secret(hr) or ""
    if not secret.endswith("-kubeconfig"):
        return set()
    return {secret, f"{secret.removesuffix('-kubeconfig')}-cluster-values"}


def chart_source_problems(
    hr: dict, lookup: Lookup, ignored: Collection[str]
) -> list[str]:
    """R1: the chart source has to exist. An ignored one isn't looked up (H4)."""
    source = chart_source(hr)
    if source is None:
        return ["has neither chartRef nor chart.spec.sourceRef"]
    if chart_source_key(hr) in ignored:
        return []
    if source[0] not in CHART_SOURCE_KINDS:
        return [f"chart source kind '{source[0]}' isn't a Flux source"]
    if lookup(*source) is None:
        return [f"chart source {source[0]} '{source[1]}/{source[2]}' doesn't exist"]
    return []


def values_from_problems(hr: dict, exempt: set[str], lookup: Lookup) -> list[str]:
    """R2: every `valuesFrom` object that isn't optional or exempt, and its key, have to exist.

    The content isn't parsed.
    """
    problems = []
    for ref in hr["spec"].get("valuesFrom") or []:
        kind, name = ref.get("kind", ""), ref.get("name", "")
        if ref.get("optional") or name in exempt:
            continue
        obj = (
            lookup(kind, hr["metadata"]["namespace"], name)
            if kind in ("ConfigMap", "Secret")
            else None
        )
        key = ref.get("valuesKey", "values.yaml")
        if obj is None:
            problems.append(f"valuesFrom {kind} '{name}' doesn't exist")
        elif key not in {**(obj.get("data") or {}), **(obj.get("binaryData") or {})}:
            problems.append(f"valuesFrom {kind} '{name}' has no key '{key}'")
    return problems


def reference_problems(
    hr: dict, hr_class: str, lookup: Lookup, ignored: Collection[str] = ()
) -> list[str]:
    """R1-R4: what the HelmRelease refers to has to exist."""
    namespace = hr["metadata"]["namespace"]
    # R3
    exempt = management_cluster_objects(hr) if hr_class == "H3b" else set()
    problems = chart_source_problems(hr, lookup, ignored)

    secret = kubeconfig_secret(hr)
    if (
        hr["spec"].get("kubeConfig")
        and secret not in exempt
        and (not secret or lookup("Secret", namespace, secret) is None)
    ):
        problems.append(f"kubeConfig Secret '{secret}' doesn't exist")

    problems += values_from_problems(hr, exempt, lookup)

    # R4
    for dep in depends_on_keys(hr):
        dep_namespace, _, dep_name = dep.partition("/")
        if lookup("HelmRelease", dep_namespace, dep_name) is None:
            problems.append(f"dependsOn HelmRelease '{dep}' doesn't exist")
    return problems
