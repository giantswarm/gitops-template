"""Checks that the clusters cluster_gates lists match the repository, and of the stand-in
`Cluster`'s condition; they need no cluster."""

from pathlib import Path

import yaml
from cluster_gates import GATES
from stand_in_clusters import available_condition

WORKLOAD_CLUSTERS_DIR = (
    Path(__file__).resolve().parent
    / "../../management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters"
)


def test_available_condition_has_a_message() -> None:
    # v1beta2 conditions require `message`, even an empty one
    condition = available_condition("False")
    assert condition["type"] == "Available"
    assert condition["status"] == "False"
    assert condition["message"] == ""


def gates_in_repository() -> dict[str, list[tuple[str, str]]]:
    """For the `Cluster` each Kustomization health-checks: that Kustomization, then the ones
    that depend on it, as `(name, path)`."""
    kustomizations = []
    for file in sorted(WORKLOAD_CLUSTERS_DIR.glob("*.yaml")):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                kustomizations.append(yaml.safe_load(f))
    clusters = {
        k["metadata"]["name"]: check["name"]
        for k in kustomizations
        for check in k["spec"].get("healthChecks") or []
        if check["kind"] == "Cluster"
    }
    gates: dict[str, list[tuple[str, str]]] = {name: [] for name in clusters.values()}
    for k in kustomizations:
        name = k["metadata"]["name"]
        if name in clusters:
            gates[clusters[name]].insert(0, (name, k["spec"]["path"]))
        for dependency in k["spec"].get("dependsOn") or []:
            gates[clusters[dependency["name"]]].append((name, k["spec"]["path"]))
    return gates


def test_gates_match_the_repository() -> None:
    gates = gates_in_repository()
    assert {
        cluster: [name for name, _ in kustomizations]
        for cluster, kustomizations in gates.items()
    } == {
        cluster: [gate.cluster_kustomization, gate.apps_kustomization]
        for cluster, gate in GATES.items()
    }
    # the cluster's Kustomization applies mapi/cluster, the apps one the rest of mapi
    for (_, cluster_path), (_, apps_path) in gates.values():
        assert cluster_path == apps_path + "/cluster"
        assert apps_path.endswith("/mapi")
