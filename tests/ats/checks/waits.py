"""Listing Flux objects and waiting for them to get ready.

The checks call these through the module, as `waits.list_objects`, so a test can stand in
for the cluster by replacing them here.
"""

import logging
import time
from collections.abc import Collection

import pykube
import pytest
from pykube.objects import APIObject

from checks.conditions import not_ready_reason, obj_key, ready

POLL_INTERVAL_SEC = 5

logger = logging.getLogger(__name__)


def list_objects(
    api: pykube.HTTPClient, obj_type: type[APIObject], ignored: Collection[str]
) -> dict[str, dict]:
    """Every `obj_type` object in the cluster by `namespace/name`, except the ignored ones."""
    objects = (o.obj for o in obj_type.objects(api).filter(namespace=pykube.all))
    return {obj_key(o): o for o in objects if obj_key(o) not in ignored}


def wait_for_ready(
    api: pykube.HTTPClient,
    obj_type: type[APIObject],
    keys: Collection[str],
    timeout_sec: int,
) -> dict[str, str]:
    """Wait for the Flux objects in `keys` to be Ready.

    Returns `namespace/name` -> reason for the ones that aren't Ready when `timeout_sec` is up.
    """
    deadline = time.time() + timeout_sec
    while True:
        current = list_objects(api, obj_type, ())
        not_ready = {
            k: (
                not_ready_reason(current[k])
                if k in current
                else "doesn't exist any more"
            )
            for k in sorted(keys)
            if k not in current or not ready(obj_type.kind, current[k])
        }
        if not not_ready or time.time() >= deadline:
            return not_ready
        logger.debug(
            f"Waiting for {len(not_ready)} {obj_type.kind} objects to be ready: "
            f"{sorted(not_ready)}"
        )
        time.sleep(POLL_INTERVAL_SEC)


def fail_on_problems(problems: list[str], what: str) -> None:
    if problems:
        for p in problems:
            logger.error(p)
        pytest.fail(f"{len(problems)} {what}:\n" + "\n".join(problems))
