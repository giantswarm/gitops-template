"""U1: what `schedule.window` does, on hello-world providers of the test's own.

Both providers have a daily cron time 12 hours away. The one with `window: 0s` reads the
registry when it's created and when its range changes all the same, and then waits for its
cron time rather than reading every 10 minutes. The one with a one-hour window exports nothing,
not even at creation, and a new range doesn't change that.
"""

from datetime import UTC, datetime, timedelta

import pykube
from checks.waits import fail_on_problems
from pykube.objects import APIObject
from resource_set_objects import (
    SKIPPED,
    SUCCEEDED,
    ResourceSetInputProviderCR,
    request,
    wait_for_reason,
)
from resource_set_status import closed_window, exported_tags, next_schedule

FIRST, SECOND = "3.2.3", "3.2.4"


def provider(api: pykube.HTTPClient, name: str, schedule: dict) -> APIObject:
    """A provider of hello-world FIRST in `default`, once Flux Operator has reconciled it."""
    obj = ResourceSetInputProviderCR(
        api,
        {
            "apiVersion": ResourceSetInputProviderCR.version,
            "kind": ResourceSetInputProviderCR.kind,
            "metadata": {"name": name, "namespace": "default"},
            "spec": {
                "type": "OCIArtifactTag",
                "url": "oci://gsoci.azurecr.io/charts/giantswarm/hello-world",
                "filter": {"semver": FIRST, "limit": 1},
                "schedule": [schedule],
            },
        },
    )
    obj.create()
    wait_for_reason(obj, SUCCEEDED, SKIPPED)
    return obj


def tags_after_new_range(zero: APIObject, closed: APIObject) -> dict[str, list[str]]:
    """What each provider exports at creation and after its range changes to SECOND."""
    tags = {"zero": exported_tags(zero.obj), "closed": exported_tags(closed.obj)}
    for obj in (zero, closed):
        request(obj, {"spec": {"filter": {"semver": SECOND}}})
    tags |= {
        "zero new": exported_tags(zero.obj),
        "closed new": exported_tags(closed.obj),
    }
    return tags


def check_schedule_window(api: pykube.HTTPClient) -> None:
    """U1: `window: 0s` keeps nothing out; a closed window keeps out every version."""
    schedule = closed_window(datetime.now(UTC))
    created: list[APIObject] = []
    try:
        created.append(provider(api, "window-zero", {**schedule, "window": "0s"}))
        created.append(provider(api, "window-closed", schedule))
        tags = tags_after_new_range(*created)
        expected = {
            "zero": [FIRST],
            "closed": [],
            "zero new": [SECOND],
            "closed new": [],
        }
        problems = [
            f"{k}: exports {tags[k]}, not {v}"
            for k, v in expected.items()
            if tags[k] != v
        ]
        # with `window: 0s`, the next read is the cron time, not the 10-minute interval
        when = next_schedule(created[0].obj)
        if when is None or when < datetime.now(UTC) + timedelta(hours=11):
            problems.append(f"zero: next read at {when}, not at its cron time")
        fail_on_problems(problems, "schedule.window problems")
    finally:
        for obj in created:
            obj.delete()
