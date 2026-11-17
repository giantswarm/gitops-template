"""K1 and S1: the Kustomizations and the sources have to get ready."""

import logging
from collections.abc import Collection

import pykube
import pytest
from pytest_helm_charts.flux.kustomization import KustomizationCR

from checks import waits
from checks.kinds import SOURCE_KINDS

FLUX_OBJECTS_READY_TIMEOUT_SEC = 60
# sources pull from a remote registry or repository, give them more time
SOURCES_READY_TIMEOUT_SEC = 180

logger = logging.getLogger(__name__)


def check_kustomizations(api: pykube.HTTPClient) -> None:
    """K1: every Kustomization gets ready, including the ones GITOPS_IGNORED_OBJECTS names.
    E2: there has to be one."""
    waited: set[str] = set()
    # The root Kustomizations create the cluster ones once they're ready, so list again
    #  until no new one appears. Otherwise the later checks could run before Flux has
    #  applied what the cluster Kustomizations create.
    while True:
        new = set(waits.list_objects(api, KustomizationCR, ())) - waited
        if not new:
            break
        waited |= new
        not_ready = waits.wait_for_ready(
            api, KustomizationCR, new, FLUX_OBJECTS_READY_TIMEOUT_SEC
        )
        waits.fail_on_problems(
            [f"Kustomization '{k}' isn't ready: {r}" for k, r in not_ready.items()],
            "Kustomizations aren't ready",
        )
    if not waited:
        pytest.fail("There is no Kustomization in the cluster.")
    logger.info(f"{len(waited)} Kustomizations are ready.")


def check_sources(api: pykube.HTTPClient, ignored: Collection[str]) -> None:
    """S1: every source of every kind that isn't ignored gets ready. E1: none is fine."""
    problems = []
    for kind in SOURCE_KINDS:
        sources = waits.list_objects(api, kind, ignored)
        if not sources:
            logger.info(f"There is no {kind.kind} to check.")
            continue
        not_ready = waits.wait_for_ready(api, kind, sources, SOURCES_READY_TIMEOUT_SEC)
        problems += [
            f"{kind.kind} '{k}' isn't ready: {r}" for k, r in not_ready.items()
        ]
        logger.info(f"Checked {len(sources)} {kind.kind} objects.")
    waits.fail_on_problems(problems, "sources aren't ready")
