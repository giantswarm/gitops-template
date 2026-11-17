"""H1-H5: which HelmReleases have to get ready."""

import re
from collections.abc import Collection

from checks.helm_release_sources import (
    Lookup,
    chart_name,
    chart_source_key,
    kubeconfig_secret,
)

# H2: Giant Swarm's charts that create a workload cluster
CLUSTER_CHART_NAME = re.compile(r"release-(aws|azure|vsphere|cloud-director)")


def classify(hr: dict, lookup: Lookup) -> str:
    """Which of H1, H2, H3a and H3b the HelmRelease is.

    A workload-cluster app is H3a when its kubeconfig Secret exists in the test cluster,
    whatever the cluster is called.
    """
    name = chart_name(hr, lookup)
    if name is not None and CLUSTER_CHART_NAME.fullmatch(name):
        return "H2"
    if not hr["spec"].get("kubeConfig"):
        return "H1"
    secret = kubeconfig_secret(hr)
    if secret and lookup("Secret", hr["metadata"]["namespace"], secret) is not None:
        return "H3a"
    return "H3b"


def depends_on_keys(hr: dict) -> list[str]:
    """`namespace/name` of each HelmRelease in `dependsOn`; the namespace defaults to the
    HelmRelease's."""
    namespace = hr["metadata"]["namespace"]
    return [
        f"{d.get('namespace', namespace)}/{d['name']}"
        for d in hr["spec"].get("dependsOn") or []
    ]


def helm_releases_to_wait_for(
    hrs: dict[str, dict], classes: dict[str, str], ignored: Collection[str]
) -> set[str]:
    """H1 and H3a, except H5: the ones whose `dependsOn` chain reaches an H2, H3b or H4, or
    whose chart source is ignored."""
    dependents: dict[str, list[str]] = {}
    for key, hr in hrs.items():
        for dep in depends_on_keys(hr):
            dependents.setdefault(dep, []).append(key)
    # walk from the HelmReleases that can't get ready to everything that depends on them
    blocked = (
        {k for k, c in classes.items() if c in ("H2", "H3b")}
        | {k for k, hr in hrs.items() if chart_source_key(hr) in ignored}
        | set(ignored)
    )
    pending = list(blocked)
    while pending:
        for dependent in dependents.get(pending.pop(), []):
            if dependent not in blocked:
                blocked.add(dependent)
                pending.append(dependent)
    return {k for k, c in classes.items() if c in ("H1", "H3a") and k not in blocked}
