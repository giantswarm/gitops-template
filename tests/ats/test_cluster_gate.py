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


Gates = dict[str, list[tuple[str, str]]]


def gates_of(kustomizations: list[dict]) -> tuple[Gates, list[str]]:
    """For the `Cluster` each of `kustomizations` health-checks: that Kustomization, then the
    ones that depend on it, as `(name, path)`; and the Kustomizations that depend on one
    without a `Cluster` health check."""
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
            if dependency["name"] not in clusters:
                problems.append(
                    f"Kustomization '{name}' depends on '{dependency['name']}', which doesn't "
                    "health-check a Cluster: give it the cluster's health check, and add the "
                    "cluster to GATES in cluster_gates.py"
                )
                continue
            gates[clusters[dependency["name"]]].append((name, k["spec"]["path"]))
    return gates, problems


def gates_in_repository() -> tuple[Gates, list[str]]:
    kustomizations = []
    for file in sorted(WORKLOAD_CLUSTERS_DIR.glob("*.yaml")):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                kustomizations.append(yaml.safe_load(f))
    return gates_of(kustomizations)


def test_gates_of_reports_a_dependency_without_a_cluster_health_check() -> None:
    kustomizations: list[dict] = [
        {"metadata": {"name": "wc"}, "spec": {"path": "./wc/mapi/cluster"}},
        {
            "metadata": {"name": "wc-apps"},
            "spec": {"path": "./wc/mapi", "dependsOn": [{"name": "wc"}]},
        },
    ]
    assert gates_of(kustomizations) == (
        {},
        [
            "Kustomization 'wc-apps' depends on 'wc', which doesn't health-check a Cluster: "
            "give it the cluster's health check, and add the cluster to GATES in "
            "cluster_gates.py"
        ],
    )


def test_gates_match_the_repository() -> None:
    gates, problems = gates_in_repository()
    assert not problems, "\n".join(problems)
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
