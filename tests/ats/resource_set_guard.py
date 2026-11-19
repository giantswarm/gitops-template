"""U3: losing the version never uninstalls the app or deletes the cluster.

Without a version, the app example's ResourceSet would render nothing and delete the
HelmReleases it rendered, which uninstalls the app from every cluster. Its `dependsOn` holds it
until the provider is Ready with a version. The check takes the version away in each way it
can go: the registry can't be read, no tag matches the range, the provider is deleted. Each
time, the ResourceSet has to wait for its provider, and the app has to stay.

The management cluster's Kustomization, which applies the example, is suspended meanwhile, so
Flux doesn't put the provider back; resuming it does. resource_set_cluster_guard does the same
for the cluster example.
"""

from collections.abc import Callable

import pykube
from checks.waits import fail_on_problems
from flux_reconcile import suspend, wait_until
from prune_source import kustomization
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from resource_set_objects import (
    APP_KUSTOMIZATION,
    APP_PROVIDER,
    APP_RELEASES,
    APP_RESOURCE_SET,
    APP_WORKLOAD,
    HANDLED_TIMEOUT_SEC,
    NAMESPACE,
    ResourceSetCR,
    ResourceSetInputProviderCR,
    get,
    install_now,
    request,
    resume,
)
from resource_set_status import not_kept, ready_reason

UNREADABLE_URL = "oci://gsoci.azurecr.io/charts/giantswarm/no-such-chart"
NO_MATCHING_RANGE = ">=1000.0.0"
# kustomize-controller's and Flux Operator's reason while a dependency isn't ready
DEPENDENCY_NOT_READY = "DependencyNotReady"
# what checks that a ResourceSet kept what it rendered: the problems, if it didn't
Kept = Callable[[], list[str]]


def app_problems(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> list[str]:
    """The HelmReleases of the app that are deleted or being deleted, and its workload if it's
    gone."""
    releases = HelmReleaseCR.objects(api).filter(namespace=NAMESPACE)
    problems = []
    for name in APP_RELEASES:
        release = releases.get_or_none(name=name)
        problems += not_kept(
            "HelmRelease", f"{NAMESPACE}/{name}", release.obj if release else None
        )
    namespace, name = APP_WORKLOAD
    deployments = pykube.Deployment.objects(workload_cluster).filter(
        namespace=namespace
    )
    if deployments.get_or_none(name=name) is None:
        problems.append(f"Deployment '{namespace}/{name}' was uninstalled")
    return problems


def held_problems(
    api: pykube.HTTPClient, resource_set: str, kept: Kept, loss: str
) -> list[str]:
    """Ask the ResourceSet to reconcile; it has to wait for its provider and keep what it
    rendered, which `kept` checks."""
    rset = get(api, ResourceSetCR, resource_set)
    request(rset, {})
    problems = kept()
    reason = ready_reason(rset.obj)
    if reason != DEPENDENCY_NOT_READY:
        problems.append(f"ResourceSet is {reason}, not {DEPENDENCY_NOT_READY}")
    return [f"{loss}: {p}" for p in problems]


def lose_version(
    api: pykube.HTTPClient, provider: str, resource_set: str, kept: Kept
) -> list[str]:
    """Take the provider's version away three times; return how what the ResourceSet
    rendered didn't stay."""
    rsip = get(api, ResourceSetInputProviderCR, provider)
    url = rsip.obj["spec"]["url"]
    # without a schedule, the provider reads the registry whenever it's asked
    request(rsip, {"spec": {"schedule": None, "url": UNREADABLE_URL}})
    problems = held_problems(api, resource_set, kept, "the registry can't be read")
    request(rsip, {"spec": {"url": url, "filter": {"semver": NO_MATCHING_RANGE}}})
    problems += held_problems(api, resource_set, kept, "no tag matches")
    rsip.delete()
    wait_until(
        lambda: [f"'{provider}' exists"] if rsip.exists() else [],
        HANDLED_TIMEOUT_SEC,
        "the provider wasn't deleted",
    )
    return problems + held_problems(api, resource_set, kept, "the provider is deleted")


def check_input_loss(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """U3, then Flux puts the provider back and the app is installed from it again."""
    root = kustomization(api, APP_KUSTOMIZATION)
    suspend(root)
    try:
        fail_on_problems(
            lose_version(
                api,
                APP_PROVIDER,
                APP_RESOURCE_SET,
                lambda: app_problems(api, workload_cluster),
            ),
            "losses of the version uninstalled",
        )
    finally:
        resume(root)
        install_now(api, APP_PROVIDER, APP_RESOURCE_SET)
