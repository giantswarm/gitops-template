"""Checks of the gates of the template's example organisation, and of the stand-in `Cluster`'s
condition; they need no cluster."""

from kind_config import kind_test_config, require_example
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
