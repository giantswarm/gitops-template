"""W1: the workloads the H3a HelmReleases install into the workload cluster."""

import time

import pykube

from checks import waits
from checks.conditions import condition_true, obj_key

# workloads in the workload cluster, once their HelmReleases are ready
WORKLOADS_AVAILABLE_TIMEOUT_SEC = 120


def deployment_available(obj: dict) -> bool:
    return condition_true(obj, "Available")


def releases_without_assertion(
    releases: dict[str, dict], assertions: list[dict]
) -> list[str]:
    """W1: the releases no assertion names in its `helmRelease` key (`namespace/name` of the
    HelmRelease whose main workload the object is). The key isn't a field of the object, so
    the comparison skips it."""
    asserted = {a.get("helmRelease") for a in assertions}
    return sorted(k for k in releases if k not in asserted)


def _deployment(api: pykube.HTTPClient, assertion: dict) -> dict:
    meta = assertion["metadata"]
    return (
        pykube.Deployment.objects(api)
        .filter(namespace=meta["namespace"])
        .get(name=meta["name"])
        .obj
    )


def unavailable_deployments(
    api: pykube.HTTPClient, assertions: list[dict]
) -> list[str]:
    """W1: wait for the Deployments the assertions name to be available.

    Returns `namespace/name` of the ones that aren't when the time is up.
    """
    deployments = [a for a in assertions if a.get("kind") == "Deployment"]
    deadline = time.time() + WORKLOADS_AVAILABLE_TIMEOUT_SEC
    while True:
        unavailable = [
            obj_key(d)
            for d in deployments
            if not deployment_available(_deployment(api, d))
        ]
        if not unavailable or time.time() >= deadline:
            return unavailable
        time.sleep(waits.POLL_INTERVAL_SEC)
