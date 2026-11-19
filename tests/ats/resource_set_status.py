"""What the status of a Flux Operator object says, and upgrade windows, without a cluster.

A `ResourceSetInputProvider` with a schedule reads its source only while a window is open:
while `now + timeout` is before the last cron time plus `window`. A schedule with
`window: 0s` keeps nothing out.
"""

from datetime import UTC, datetime, timedelta

# Open whenever it's asked: the last cron time is at most a minute ago, and five minutes is
#  more than that plus Flux Operator's default timeout of two minutes.
OPEN_WINDOW = {"cron": "* * * * *", "timeZone": "UTC", "window": "5m"}


def closed_window(now: datetime) -> dict:
    """A daily one-hour window that starts 12 hours after `now`: closed for the next 11 hours."""
    start = now.astimezone(UTC) + timedelta(hours=12)
    return {
        "cron": f"{start.minute} {start.hour} * * *",
        "timeZone": "UTC",
        "window": "1h",
    }


def exported_tags(rsip: dict) -> list[str]:
    """The tags a `ResourceSetInputProvider` of an OCI type exports, highest first."""
    inputs = (rsip.get("status") or {}).get("exportedInputs") or []
    return [i["tag"] for i in inputs]


def ready_reason(obj: dict) -> str:
    """The reason of the Ready condition, or "" without one."""
    conditions = (obj.get("status") or {}).get("conditions") or []
    return next(
        (c.get("reason", "") for c in conditions if c.get("type") == "Ready"), ""
    )


def next_schedule(rsip: dict) -> datetime | None:
    """When the provider reads its source next, if a schedule decides it."""
    when = ((rsip.get("status") or {}).get("nextSchedule") or {}).get("when")
    return datetime.fromisoformat(when) if when else None


def handled(obj: dict, token: str) -> bool:
    """Whether Flux Operator has handled the reconcile request `token`, whatever it did."""
    return (obj.get("status") or {}).get("lastHandledReconcileAt") == token
