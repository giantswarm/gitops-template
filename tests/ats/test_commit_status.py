"""Checks of how commit_status suspends the Alert and judges the Receiver; they need no
cluster."""

from commit_status import receiver_problems, suspended

READY = {"conditions": [{"type": "Ready", "status": "True"}]}


def test_suspended_sets_suspend() -> None:
    alert = {"metadata": {"name": "a"}, "spec": {"eventSeverity": "info"}}
    assert suspended(alert) == {
        "metadata": {"name": "a"},
        "spec": {"eventSeverity": "info", "suspend": True},
    }
    # the manifest read from the repository stays as it is
    assert "suspend" not in alert["spec"]


def test_receiver_problems_ready() -> None:
    receiver = {"metadata": {"name": "r", "namespace": "default"}, "status": READY}
    assert receiver_problems(receiver) == []


def test_receiver_problems_not_ready() -> None:
    receiver = {
        "metadata": {"name": "r", "namespace": "default"},
        "status": {
            "conditions": [{"type": "Ready", "status": "False", "message": "no"}]
        },
    }
    assert receiver_problems(receiver) == ["Receiver 'default/r': Ready is False: no"]


def test_receiver_problems_missing() -> None:
    assert receiver_problems(None) == ["the Receiver isn't there"]
