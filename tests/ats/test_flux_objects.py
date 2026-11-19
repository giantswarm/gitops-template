"""The kind test: what Flux applies from the repository has to get ready and match the
assertions. The checks are in `checks`."""

from collections.abc import Iterator

import pykube
import pytest
from automation_access import (
    access_problems,
    api_server_review,
    expected_access,
    org_namespace,
)
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
from cluster_gate import check_cluster_gate
from conftest import GitOpsTestConfig
from node_pools import node_pool_problems_in_cluster
from notification_objects import check_notifications
from prune_checks import check_prune
from pytest_helm_charts.clusters import Cluster
from resource_set_guard import check_input_loss
from resource_set_objects import EXAMPLES, install_now
from resource_set_schedule import check_schedule_window
from resource_set_upgrade import check_scheduled_cluster_upgrade
from shared_objects import check_shared_object_copied
from stand_in_clusters import stand_in_clusters
from values_watch import check_values_change_applied
from workload_cluster_secrets import check_secrets_pushed

# Kyverno has to run before gitops_deployment installs External Secrets Operator, and Flux
#  Operator before it applies the repository: pytest sets up the fixtures of `usefixtures`
#  before the ones a test requests.
#  The Alert of the notification example has to be suspended before then, too.
pytestmark = pytest.mark.usefixtures("kyverno", "suspended_alert", "flux_operator")


@pytest.fixture(scope="module")
def cluster_gate_problems(
    kube_cluster: Cluster, gitops_deployment: None
) -> Iterator[list[str]]:
    # The cluster Kustomizations get ready only once their stand-in Cluster is Available, so
    #  this runs before the Kustomizations are checked; test_apps_wait_for_cluster reports it.
    clusters = stand_in_clusters(kube_cluster.kube_client)
    yield check_cluster_gate(clusters)
    for cluster in clusters:
        cluster.delete()


@pytest.fixture(scope="module")
def check_kustomizations_successful(
    kube_cluster: Cluster, gitops_deployment: None, cluster_gate_problems: list[str]
) -> None:
    check_kustomizations(kube_cluster.kube_client)


def test_kustomizations_successful(check_kustomizations_successful: None) -> None:
    # all the checks are done actually in the fixture, which was extracted to avoid
    #  duplication in other tests
    pass


def test_automation_access(
    kube_cluster: Cluster,
    gitops_test_config: GitOpsTestConfig,
    automation_rbac: None,
    check_kustomizations_successful: None,
) -> None:
    # the `automation` ServiceAccounts have the rights of a management cluster, no more and no
    #  less, once the repository is applied: SubjectAccessReviews also catch what other objects,
    #  such as ones left over from an earlier run, grant them
    org = org_namespace(gitops_test_config.init_namespaces)
    assert org, "GITOPS_INIT_NAMESPACES has no `org-*` namespace"
    review = api_server_review(kube_cluster.kube_client)
    problems = access_problems(review, expected_access(org))
    assert not problems, "\n".join(problems)


@pytest.fixture(scope="module")
def resource_sets_installed(
    kube_cluster: Cluster, check_kustomizations_successful: None
) -> None:
    # The ResourceSets render sources and HelmReleases, so the checks of those wait for them.
    for provider, resource_set in EXAMPLES:
        install_now(kube_cluster.kube_client, provider, resource_set)


def test_resource_sets_installed(resource_sets_installed: None) -> None:
    # all the checks are done actually in the fixture, which the source and HelmRelease
    #  checks need
    pass


@pytest.fixture(scope="module")
def check_sources_successful(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
    resource_sets_installed: None,
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
    resource_sets_installed: None,
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


def test_secrets_pushed(
    workload_cluster: pykube.HTTPClient,
    check_kustomizations_successful: None,
) -> None:
    check_secrets_pushed(workload_cluster)


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


def test_shared_object_copied(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
) -> None:
    check_shared_object_copied(kube_cluster.kube_client)


def test_commit_status_notifications(
    kube_cluster: Cluster,
    check_kustomizations_successful: None,
) -> None:
    # N1: ESO wrote the tokens and the Receiver is Ready; assertions/exists/notifications checks
    #  the Provider and the Alert
    check_notifications(kube_cluster.kube_client)


def test_apps_wait_for_cluster(cluster_gate_problems: list[str]) -> None:
    # G1: a cluster's apps Kustomizations apply nothing until the cluster is Available
    assert not cluster_gate_problems, "\n".join(cluster_gate_problems)


def test_schedule_window(kube_cluster: Cluster, resource_sets_installed: None) -> None:
    check_schedule_window(kube_cluster.kube_client)


def test_scheduled_cluster_upgrade(
    kube_cluster: Cluster, check_helm_release_successful: dict[str, dict]
) -> None:
    check_scheduled_cluster_upgrade(kube_cluster.kube_client)


def test_input_loss_keeps_the_app(
    kube_cluster: Cluster,
    workload_cluster: pykube.HTTPClient,
    check_helm_release_successful: dict[str, dict],
) -> None:
    check_input_loss(kube_cluster.kube_client, workload_cluster)


# must stay last: it deletes what the tests above check
def test_prune(
    request: pytest.FixtureRequest,
    kube_cluster: Cluster,
    workload_cluster: pykube.HTTPClient,
    check_helm_release_successful: dict[str, dict],
) -> None:
    check_prune(request, kube_cluster.kube_client, workload_cluster)
