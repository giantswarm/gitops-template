"""The clusters of the template's example organisation whose apps wait for them, as the
repository's Kustomizations say, so that test_cluster_gate can check them without a cluster.
"""

from pathlib import Path

import yaml

ORG_DIR = (
    Path(__file__).resolve().parent
    / "../../management-clusters/MC_NAME/organizations/ORG_NAME"
)
# the workload clusters' Flux Kustomizations, next to the directories they apply, one per cluster.
#  The organisation's namespace Kustomization applies them into its namespace, through
#  namespace/kustomization.yaml, which lists ../workload-clusters.
WORKLOAD_CLUSTERS_DIR = ORG_DIR / "workload-clusters"
# the organisation's namespace Kustomization, which every cluster Kustomization depends on
ORGANIZATION_KUSTOMIZATION_FILE = ORG_DIR / "namespace.yaml"
# for each `Cluster`: the Kustomization that health-checks it, then the ones that depend on
#  that one, as `(name, path)`
Gates = dict[str, list[tuple[str, str]]]


def gates_of(
    kustomizations: list[dict], organization_kustomization: str
) -> tuple[Gates, list[str]]:
    """The gates of `kustomizations`, and the Kustomizations that depend on one without a
    `Cluster` health check. A dependency on the organisation's namespace Kustomization,
    `organization_kustomization`, which applies them, gates no cluster."""
    clusters = {
        k["metadata"]["name"]: check["name"]
        for k in kustomizations
        for check in k["spec"].get("healthChecks") or []
        if check["kind"] == "Cluster"
    }
    gates: Gates = {name: [] for name in clusters.values()}
    problems = []
    for k in kustomizations:
        name = k["metadata"]["name"]
        if name in clusters:
            gates[clusters[name]].insert(0, (name, k["spec"]["path"]))
        for dependency in k["spec"].get("dependsOn") or []:
            if dependency["name"] == organization_kustomization:
                continue
            if dependency["name"] not in clusters:
                problems.append(
                    f"Kustomization '{name}' depends on '{dependency['name']}', which doesn't "
                    "health-check a Cluster: give it the cluster's health check"
                )
                continue
            gates[clusters[dependency["name"]]].append((name, k["spec"]["path"]))
    return gates, problems


def _workload_cluster_kustomizations() -> list[dict]:
    kustomizations = []
    for file in sorted(WORKLOAD_CLUSTERS_DIR.glob("*.yaml")):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                kustomizations.append(yaml.safe_load(f))
    return kustomizations


def cluster_health_exprs() -> dict[str, list[str]]:
    """The `current` expressions each workload cluster Kustomization that health-checks a
    `Cluster` has for the kind `Cluster`, by its name."""
    return {
        k["metadata"]["name"]: [
            e["current"]
            for e in k["spec"].get("healthCheckExprs") or []
            if e["kind"] == "Cluster"
        ]
        for k in _workload_cluster_kustomizations()
        if any(c["kind"] == "Cluster" for c in k["spec"].get("healthChecks") or [])
    }


def gates_in_repository() -> tuple[Gates, list[str]]:
    """The gates of the workload cluster Kustomizations in the repository."""
    with ORGANIZATION_KUSTOMIZATION_FILE.open() as f:
        organization_kustomization = yaml.safe_load(f)["metadata"]["name"]
    return gates_of(_workload_cluster_kustomizations(), organization_kustomization)
