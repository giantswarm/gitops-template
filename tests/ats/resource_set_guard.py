"""U3: losing the version never uninstalls the app.

Without a version, the app example's ResourceSet would render nothing and delete the
HelmReleases it rendered, which uninstalls the app from every cluster. Its `dependsOn` holds it
until the provider is Ready with a version. The check takes the version away in each way it
can go: the registry can't be read, no tag matches the range, the provider is deleted. Each
time, the ResourceSet has to wait for its provider, and the app has to stay.

The management cluster's Kustomization, which applies the example, is suspended meanwhile, so
Flux doesn't put the provider back; resuming it does.
"""

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
from resource_set_status import ready_reason

UNREADABLE_URL = "oci://gsoci.azurecr.io/charts/giantswarm/no-such-chart"
NO_MATCHING_RANGE = ">=1000.0.0"
# kustomize-controller's and Flux Operator's reason while a dependency isn't ready
DEPENDENCY_NOT_READY = "DependencyNotReady"


def app_problems(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> list[str]:
    """The HelmReleases and the workload of the app that are gone."""
    releases = HelmReleaseCR.objects(api).filter(namespace=NAMESPACE)
    problems = [
        f"HelmRelease '{NAMESPACE}/{name}' was deleted"
        for name in APP_RELEASES
        if releases.get_or_none(name=name) is None
    ]
    namespace, name = APP_WORKLOAD
    deployments = pykube.Deployment.objects(workload_cluster).filter(
        namespace=namespace
    )
    if deployments.get_or_none(name=name) is None:
        problems.append(f"Deployment '{namespace}/{name}' was uninstalled")
    return problems


def held_problems(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient, loss: str
) -> list[str]:
    """Ask the ResourceSet to reconcile; it has to wait for its provider and keep the app."""
    rset = get(api, ResourceSetCR, APP_RESOURCE_SET)
    request(rset, {})
    problems = app_problems(api, workload_cluster)
    reason = ready_reason(rset.obj)
    if reason != DEPENDENCY_NOT_READY:
        problems.append(f"ResourceSet is {reason}, not {DEPENDENCY_NOT_READY}")
    return [f"{loss}: {p}" for p in problems]


def lose_version(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> list[str]:
    """Take the version away three times; return how the app didn't stay."""
    rsip = get(api, ResourceSetInputProviderCR, APP_PROVIDER)
    url = rsip.obj["spec"]["url"]
    # without a schedule, the provider reads the registry whenever it's asked
    request(rsip, {"spec": {"schedule": None, "url": UNREADABLE_URL}})
    problems = held_problems(api, workload_cluster, "the registry can't be read")
    request(rsip, {"spec": {"url": url, "filter": {"semver": NO_MATCHING_RANGE}}})
    problems += held_problems(api, workload_cluster, "no tag matches")
    rsip.delete()
    wait_until(
        lambda: [f"'{APP_PROVIDER}' exists"] if rsip.exists() else [],
        HANDLED_TIMEOUT_SEC,
        "the provider wasn't deleted",
    )
    return problems + held_problems(api, workload_cluster, "the provider is deleted")


def check_input_loss(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> None:
    """U3, then Flux puts the provider back and the app is installed from it again."""
    root = kustomization(api, APP_KUSTOMIZATION)
    suspend(root)
    try:
        fail_on_problems(
            lose_version(api, workload_cluster), "losses of the version uninstalled"
        )
    finally:
        resume(root)
        install_now(api, APP_PROVIDER, APP_RESOURCE_SET)
