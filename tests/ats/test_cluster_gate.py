"""Checks that the clusters cluster_gates lists match the repository, and of the stand-in
`Cluster`'s condition; they need no cluster."""

from cluster_gates import GATES
from repository_gates import gates_in_repository, gates_of
from stand_in_clusters import available_condition


def test_available_condition_has_a_message() -> None:
    # v1beta2 conditions require `message`, even an empty one
    condition = available_condition("False")
    assert condition["type"] == "Available"
    assert condition["status"] == "False"
    assert condition["message"] == ""


def test_gates_of_reports_a_dependency_without_a_cluster_health_check() -> None:
    kustomizations: list[dict] = [
        {"metadata": {"name": "wc"}, "spec": {"path": "./wc/cluster"}},
        {
            "metadata": {"name": "wc-apps"},
            "spec": {"path": "./wc", "dependsOn": [{"name": "wc"}]},
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
    # the cluster's Kustomization applies cluster/, the apps one the cluster's directory
    for (_, cluster_path), (_, apps_path) in gates.values():
        assert cluster_path == apps_path + "/cluster"
