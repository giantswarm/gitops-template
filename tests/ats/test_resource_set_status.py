"""Checks of how the ResourceSet tests read Flux Operator objects and pick a closed upgrade
window; they need no cluster."""

from datetime import UTC, datetime

from resource_set_status import (
    closed_window,
    exported_tags,
    handled,
    next_schedule,
    ready_reason,
)


def test_exported_tags() -> None:
    rsip = {"status": {"exportedInputs": [{"id": "1", "tag": "3.2.4"}]}}
    assert exported_tags(rsip) == ["3.2.4"]


def test_exported_tags_of_a_provider_without_inputs() -> None:
    # Flux Operator leaves `exportedInputs` out when it exports nothing
    assert exported_tags({"status": {}}) == []
    assert exported_tags({}) == []


def test_ready_reason() -> None:
    obj = {
        "status": {
            "conditions": [
                {"type": "Reconciling", "status": "True", "reason": "Progressing"},
                {"type": "Ready", "status": "False", "reason": "DependencyNotReady"},
            ]
        }
    }
    assert ready_reason(obj) == "DependencyNotReady"


def test_ready_reason_without_conditions() -> None:
    assert ready_reason({"status": {}}) == ""


def test_next_schedule() -> None:
    rsip = {
        "status": {
            "nextSchedule": {"cron": "0 2 * * 2", "when": "2026-11-24T02:00:00Z"}
        }
    }
    assert next_schedule(rsip) == datetime(2026, 11, 24, 2, tzinfo=UTC)


def test_next_schedule_without_one() -> None:
    assert next_schedule({"status": {}}) is None


def test_handled() -> None:
    obj = {"status": {"lastHandledReconcileAt": "token"}}
    assert handled(obj, "token")
    assert not handled(obj, "other")
    assert not handled({}, "token")


def test_closed_window_starts_12_hours_away() -> None:
    now = datetime(2026, 11, 19, 15, 42, tzinfo=UTC)
    assert closed_window(now) == {
        "cron": "42 3 * * *",
        "timeZone": "UTC",
        "window": "1h",
    }


def test_closed_window_converts_to_utc() -> None:
    # 09:05 in UTC+2 is 07:05 UTC, so the window starts at 19:05 UTC
    now = datetime.fromisoformat("2026-11-19T09:05:00+02:00")
    assert closed_window(now)["cron"] == "5 19 * * *"
