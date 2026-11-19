"""H1-H5 and R1-R4: the HelmReleases that can get ready have to, and what they refer to has
to exist."""

import logging
from collections.abc import Collection

import pykube
from pytest_helm_charts.flux.helm_release import HelmReleaseCR

from checks import waits
from checks.helm_release_classes import classify, helm_releases_to_wait_for
from checks.helm_release_references import reference_problems
from checks.helm_release_sources import cluster_lookup

# HelmReleases wait for their dependencies, pull images and run hook Jobs. Longer than the
#  examples' `timeout` of 10m, so a release that doesn't get ready reports helm-controller's
#  reason, such as the resources it waited for, instead of being caught mid-install.
HELM_RELEASES_READY_TIMEOUT_SEC = 720

logger = logging.getLogger(__name__)


def check_helm_releases(
    api: pykube.HTTPClient, ignored: Collection[str]
) -> dict[str, dict]:
    """H1-H5 and R1-R4. Returns every H3a HelmRelease, by `namespace/name`, for W1.

    The references are checked before the wait, so a missing one fails at once instead of
    after the wait for the releases that can't get ready without it.
    """
    # H4: the ignored ones aren't looked at at all
    hrs = waits.list_objects(api, HelmReleaseCR, ignored)
    if not hrs:
        logger.info("There is no HelmRelease to check.")
        return {}

    lookup = cluster_lookup(api)
    classes = {k: classify(hr, lookup) for k, hr in hrs.items()}
    for k in sorted(hrs):
        logger.info(f"HelmRelease '{k}': {classes[k]}")
    waits.fail_on_problems(
        [
            f"HelmRelease '{k}': {p}"
            for k in sorted(hrs)
            for p in reference_problems(hrs[k], classes[k], lookup, ignored)
        ],
        f"reference problems in {len(hrs)} HelmReleases",
    )

    to_wait = helm_releases_to_wait_for(hrs, classes, ignored)
    logger.info(f"Waiting for {len(to_wait)} HelmReleases: {sorted(to_wait)}")
    not_ready = waits.wait_for_ready(
        api, HelmReleaseCR, to_wait, HELM_RELEASES_READY_TIMEOUT_SEC
    )
    waits.fail_on_problems(
        [f"HelmRelease '{k}' isn't ready: {r}" for k, r in not_ready.items()],
        "HelmReleases aren't ready",
    )
    return {k: hr for k, hr in hrs.items() if classes[k] == "H3a"}
