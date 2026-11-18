"""The kind test: what Flux applies from the repository has to get ready and match the
assertions. The checks are in `checks`."""

import pykube
import pytest
from checks.assertion_files import (
    EXISTS_ASSERTIONS_DIR,
    WORKLOAD_CLUSTER_ASSERTIONS_DIR,
    all_assertions,
    load_assertions,
)
from checks.assertions import check_assertions
from checks.flux_readiness import check_kustomizations, check_sources
from checks.helm_releases import check_helm_releases
from checks.workloads import releases_without_assertion, unavailable_deployments
from conftest import GitOpsTestConfig
from node_pools import node_pool_problems_in_cluster
from prune_checks import check_prune
from pytest_helm_charts.clusters import Cluster
from values_watch import check_values_change_applied


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None
) -> None:
    check_kustomizations(kube_cluster.kube_client)


def test_kustomizations_successful(check_kustomizations_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid
    #  duplication in other tests
    pass


@pytest.fixture(scope="module")
def check_sources_successful(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
    gitops_test_config: GitOpsTestConfig,
) -> None:
    check_sources(kube_cluster.kube_client, gitops_test_config.ignored_objects)


def test_sources_successful(check_sources_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid
    #  duplication in other tests
    pass


@pytest.fixture(scope="module")
def check_helm_release_successful(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
    gitops_test_config: GitOpsTestConfig,
) -> dict[str, dict]:
    return check_helm_releases(
        kube_cluster.kube_client, gitops_test_config.ignored_objects
    )


def test_helm_release_successful(check_helm_release_successful: dict) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid
    #  duplication in other tests
    pass


def test_positive_assertions(
    kube_cluster: Cluster,
    gitops_deployment: None,
    check_helm_release_successful: dict,
    check_kustomizations_successful: None,
) -> None:
    checked = check_assertions(kube_cluster.kube_client, load_assertions())
    assert checked > 0, f"No assertions found in '{EXISTS_ASSERTIONS_DIR}'."


def test_workload_cluster_assertions(
    workload_cluster: pykube.HTTPClient,
    check_kustomizations_successful: None,
    check_helm_release_successful: dict[str, dict],
) -> None:
    # The -direct out-of-band Kustomization and the H3a HelmReleases install into the
    #  workload cluster through its kubeconfig Secret; the test's vCluster stands in for it.
    assertions = load_assertions(WORKLOAD_CLUSTER_ASSERTIONS_DIR)
    checked = check_assertions(workload_cluster, assertions)
    assert checked > 0, f"No assertions found in '{WORKLOAD_CLUSTER_ASSERTIONS_DIR}'."

    # W1: every H3a release has an assertion of its main workload
    missing = releases_without_assertion(
        check_helm_release_successful, all_assertions(assertions)
    )
    assert not missing, (
        f"H3a HelmReleases without an assertion of their main workload, one with "
        f"`helmRelease: <namespace>/<name>`, in '{WORKLOAD_CLUSTER_ASSERTIONS_DIR}': "
        f"{missing}"
    )

    # W1: the Deployments the assertions name have to be available, too
    unavailable = unavailable_deployments(workload_cluster, all_assertions(assertions))
    assert (
        not unavailable
    ), f"Deployments in the workload cluster aren't available: {unavailable}"


def test_node_pools(
    kube_cluster: Cluster,
    check_helm_release_successful: dict[str, dict],
    gitops_test_config: GitOpsTestConfig,
) -> None:
    problems = node_pool_problems_in_cluster(
        kube_cluster.kube_client, gitops_test_config.ignored_objects
    )
    assert not problems, "\n".join(problems)


def test_values_change_applied_at_once(
    kube_cluster: Cluster,
    check_helm_release_successful: dict[str, dict],
) -> None:
    check_values_change_applied(kube_cluster.kube_client)


# must stay last: it deletes what the tests above check
def test_prune(
    request: pytest.FixtureRequest,
    kube_cluster: Cluster,
    workload_cluster: pykube.HTTPClient,
    check_helm_release_successful: dict[str, dict],
) -> None:
    check_prune(request, kube_cluster.kube_client, workload_cluster)
