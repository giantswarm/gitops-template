"""Checks of the gates of the template's example organisation, and of the stand-in `Cluster`'s
condition; they need no cluster."""

import re

from cluster_gates import CLUSTER_HEALTH_EXPR, CONTROL_PLANE_CONDITIONS
from kind_config import kind_test_config, require_example
from repository_gates import cluster_health_exprs, gates_in_repository, gates_of
from stand_in_clusters import stand_in_conditions


def test_stand_in_conditions_have_a_message() -> None:
    # v1beta2 conditions require `message`, even an empty one
    for condition in stand_in_conditions("False"):
        assert condition["message"] == ""


def test_stand_in_cluster_is_short_of_workers_either_way() -> None:
    # a node pool below its minimum: Cluster API reports the cluster not Available, and the gate
    #  has to open all the same once the control plane is up
    for control_plane in ("False", "True"):
        statuses = {c["type"]: c["status"] for c in stand_in_conditions(control_plane)}
        assert statuses["Available"] == "False"
        assert statuses["WorkersAvailable"] == "False"
        for condition in CONTROL_PLANE_CONDITIONS:
            assert statuses[condition] == control_plane


def test_cluster_health_expr_waits_for_the_control_plane_only() -> None:
    assert re.findall(r"c\.type == '(\w+)'", CLUSTER_HEALTH_EXPR) == list(
        CONTROL_PLANE_CONDITIONS
    )


def test_cluster_kustomizations_wait_for_the_control_plane() -> None:
    # every Kustomization of the example organisation that health-checks a Cluster counts it as
    #  healthy once its control plane is available and reachable, not once every node pool is
    require_example("organisation")
    exprs = cluster_health_exprs()
    gates, _ = gates_in_repository()
    assert set(exprs) == {kustomizations[0][0] for kustomizations in gates.values()}
    assert {name: e for name, e in exprs.items() if e != [CLUSTER_HEALTH_EXPR]} == {}


def test_gates_of_reports_a_dependency_without_a_cluster_health_check() -> None:
    kustomizations: list[dict] = [
        {"metadata": {"name": "wc"}, "spec": {"path": "./wc/cluster"}},
        {
            "metadata": {"name": "wc-apps"},
            "spec": {"path": "./wc", "dependsOn": [{"name": "wc"}]},
        },
    ]
    assert gates_of(kustomizations, "mc-organization") == (
        {},
        [
            "Kustomization 'wc-apps' depends on 'wc', which doesn't health-check a Cluster: "
            "give it the cluster's health check"
        ],
    )


def test_gates_of_leaves_out_the_organisation_namespace_kustomization() -> None:
    # every cluster Kustomization depends on the organisation's namespace Kustomization, which
    #  applies it: that's no cluster's gate
    organization = {"name": "mc-organization", "namespace": "default"}
    kustomizations: list[dict] = [
        {
            "metadata": {"name": "wc"},
            "spec": {
                "path": "./wc/cluster",
                "dependsOn": [organization],
                "healthChecks": [{"kind": "Cluster", "name": "wc"}],
            },
        },
        {
            "metadata": {"name": "wc-apps"},
            "spec": {"path": "./wc", "dependsOn": [{"name": "wc"}]},
        },
    ]
    assert gates_of(kustomizations, "mc-organization") == (
        {"wc": [("wc", "./wc/cluster"), ("wc-apps", "./wc")]},
        [],
    )


def test_gates_match_the_repository() -> None:
    require_example("organisation")
    gates, problems = gates_in_repository()
    assert not problems, "\n".join(problems)
    # the cluster's Kustomization applies cluster/, the apps one the cluster's directory
    for (_, cluster_path), (_, apps_path) in gates.values():
        assert cluster_path == apps_path + "/cluster"
    # every cluster with base apps in kind-test.yaml has a gate
    assert {
        key.split("/")[1] for key in kind_test_config().cluster_base_apps()
    } <= gates.keys()
