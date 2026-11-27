"""P1-P4: what Flux deletes when files are deleted from Git, and what it keeps.

test_prune removes objects the other kind tests check, so it has to run after them, and it
needs their environment, which is module-scoped like every pytest-helm-charts fixture. So it is
the last test of test_flux_objects and calls `check_prune` from here; flux_inventory holds what
can be checked without a cluster.
"""

import pykube
import pytest
from checks.waits import fail_on_problems
from flux_reconcile import wait_until
from prune_cluster import (
    delete_cluster_kustomizations,
    direct_problems,
    remove_team,
    workload_problems,
)
from prune_objects import (
    KEPT_BY_FAILED_BUILD,
    KEPT_BY_GUARD,
    KEPT_BY_WAITING_ORGANIZATION,
    PROTECTED_CLUSTER,
    PRUNE_IGNORE,
    PRUNE_TIMEOUT_SEC,
    PRUNED_OBJECTS,
    PRUNED_WORKLOAD,
    UNINSTALL_TIMEOUT_SEC,
    deleted_problems,
    kept_problems,
)
from prune_patches import delete_patches
from prune_source import (
    leave_out_of_root,
    put_back_into_root,
    recover_source,
    remove_from_source,
    restore_source,
)


def tests_not_run_before(request: pytest.FixtureRequest) -> list[str]:
    """The other tests of the module that pytest doesn't run before this one in this session,
    for example because of `-k`, `--lf`, `--ff` or `--sw`."""
    items = request.session.items
    before = {
        i.originalname
        for i in items[: items.index(request.node)]
        if i.module is request.module
    }
    module_tests = {n for n in dir(request.module) if n.startswith("test_")}
    return sorted(module_tests - before - {request.node.originalname})


def app_problems(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> list[str]:
    """The objects of the removed app that still exist, in either cluster."""
    problems = deleted_problems(api, PRUNED_OBJECTS)
    namespace, name = PRUNED_WORKLOAD
    deployments = pykube.Deployment.objects(workload_cluster).filter(
        namespace=namespace
    )
    if deployments.get_or_none(name=name) is not None:
        problems.append(
            f"Deployment '{namespace}/{name}' wasn't deleted from the workload cluster"
        )
    return problems


def check_removed_files(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """P1: removing an app's files removes the app. P2: removing the organisation's
    Organization alone fails the management cluster's build, which then prunes nothing, and the
    organisation's namespace Kustomization waits for it: the Organization, the organisation's
    namespace Kustomization and the cluster's Kustomizations stay. Once the files are back,
    they're Ready again, so P3's apps Kustomization doesn't wait for them."""
    remove_from_source(api, PRUNE_IGNORE, delete_patches(PRUNED_OBJECTS))
    wait_until(
        lambda: app_problems(api, workload_cluster),
        PRUNE_TIMEOUT_SEC,
        "the removed app wasn't deleted",
    )
    fail_on_problems(
        kept_problems(api, KEPT_BY_FAILED_BUILD + KEPT_BY_WAITING_ORGANIZATION),
        "the failed build didn't keep the organisation's objects",
    )
    recover_source(api)


def check_removed_parent(api: pykube.HTTPClient) -> None:
    """P4: dropping the organisation's namespace Kustomization from the management cluster's
    build, as deleting or renaming its file does, leaves it. Its `kustomize.toolkit.fluxcd.io/
    prune: disabled` annotation keeps the management cluster's Kustomization from deleting it,
    and so its finalizer from deleting the cluster's Kustomizations. Once it's back in the build,
    the management cluster's Kustomization applies it again."""
    leave_out_of_root(api)
    fail_on_problems(
        kept_problems(api, KEPT_BY_GUARD),
        "the organisation's namespace Kustomization wasn't kept",
    )
    put_back_into_root(api)


def check_removed_cluster(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """P3: deleting a cluster as the getting-started guides do, its application team first,
    then its Kustomizations and its -direct one, deletes what they applied, from both clusters,
    except the cluster's HelmRelease and OCIRepository."""
    remove_team(api, workload_cluster)
    applied, direct_applied = delete_cluster_kustomizations(api)
    not_applied = [o for o in PROTECTED_CLUSTER if o not in applied]
    if not_applied:
        pytest.fail(f"The cluster's Kustomizations didn't apply {not_applied}.")
    if not direct_applied:
        pytest.fail("The cluster's -direct Kustomization didn't apply anything.")
    deleted = sorted(applied - set(PROTECTED_CLUSTER))
    wait_until(
        lambda: deleted_problems(api, deleted)
        + workload_problems(workload_cluster, applied)
        + direct_problems(workload_cluster, direct_applied),
        UNINSTALL_TIMEOUT_SEC,
        "the cluster's objects weren't deleted",
    )
    fail_on_problems(kept_problems(api, PROTECTED_CLUSTER), "the cluster wasn't kept")


def check_prune(
    request: pytest.FixtureRequest,
    api: pykube.HTTPClient,
    workload_cluster: pykube.HTTPClient,
) -> None:
    """P1-P4 on the out-of-band-no-flux cluster, whose apps run in the test's vCluster."""
    not_run = tests_not_run_before(request)
    if not_run:
        pytest.fail(
            f"test_prune deletes what other tests check, so it runs after them: {not_run} "
            "don't run before it. Run the whole module, in file order."
        )
    try:
        check_removed_files(api, workload_cluster)
        check_removed_parent(api)
        check_removed_cluster(api, workload_cluster)
    finally:
        restore_source(api)
