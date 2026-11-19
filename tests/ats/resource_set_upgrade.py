"""U2: the cluster example's release moves to a new version only inside its window.

The check starts the cluster from an older release, gives the provider the example's range
back with the window closed, where the release has to stay, then opens the window, where it
has to move to the newest of the range. The cluster's Kustomization is suspended meanwhile, so
Flux doesn't put the provider back; resuming it does.
"""

from datetime import UTC, datetime

import pykube
import pytest
from checks.kinds import OCIRepositoryCR
from flux_reconcile import suspend, wait_until
from prune_source import kustomization
from pykube.objects import APIObject
from resource_set_objects import (
    CLUSTER_KUSTOMIZATION,
    CLUSTER_PROVIDER,
    CLUSTER_SOURCE,
    READY_TIMEOUT_SEC,
    ResourceSetInputProviderCR,
    get,
    provider_tags,
    request,
    resume,
)
from resource_set_status import OPEN_WINDOW, closed_window

# a release-aws release below the newest of the example's range
OLDER_RELEASE = "36.1.1"


def source_tag(api: pykube.HTTPClient) -> str:
    return get(api, OCIRepositoryCR, CLUSTER_SOURCE).obj["spec"]["ref"]["tag"]


def move(api: pykube.HTTPClient, rsip: APIObject, spec: dict, tag: str) -> None:
    """Change the provider's spec and wait for the cluster's OCIRepository to get `tag`."""
    request(rsip, {"spec": spec})

    def elsewhere() -> list[str]:
        actual = source_tag(api)
        return [] if actual == tag else [f"the release is {actual}, not {tag}"]

    wait_until(elsewhere, READY_TIMEOUT_SEC, "the cluster's release didn't move")


def check_scheduled_cluster_upgrade(api: pykube.HTTPClient) -> None:
    """U2: the cluster's release moves to the newest of its range only inside the window."""
    cluster = kustomization(api, CLUSTER_KUSTOMIZATION)
    suspend(cluster)
    try:
        rsip = get(api, ResourceSetInputProviderCR, CLUSTER_PROVIDER)
        newest = provider_tags(api, CLUSTER_PROVIDER)[0]
        if newest == OLDER_RELEASE:
            pytest.fail(f"{OLDER_RELEASE} is the newest release of the range.")
        example = {"semver": rsip.obj["spec"]["filter"]["semver"]}
        move(
            api,
            rsip,
            {"schedule": [OPEN_WINDOW], "filter": {"semver": OLDER_RELEASE}},
            OLDER_RELEASE,
        )
        closed = closed_window(datetime.now(UTC))
        request(rsip, {"spec": {"schedule": [closed], "filter": example}})
        moved = [provider_tags(api, CLUSTER_PROVIDER), source_tag(api)]
        if moved != [[OLDER_RELEASE], OLDER_RELEASE]:
            pytest.fail(f"The release moved outside the window: {moved}")
        move(api, rsip, {"schedule": [OPEN_WINDOW]}, newest)
    finally:
        resume(cluster)
