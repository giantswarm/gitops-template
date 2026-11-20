"""Checks of what checks.conditions says about a Flux object whose Ready condition isn't the
first; they need no cluster."""

from checks.conditions import is_ready, not_ready_reason

READY = {"type": "Ready", "status": "True", "message": "Applied revision"}
NOT_READY = {"type": "Ready", "status": "False", "message": "install failed"}
RELEASED = {"type": "Released", "status": "True", "message": "Helm install succeeded"}
RECONCILING = {"type": "Reconciling", "status": "True", "message": "Detecting drift"}


def test_later_ready_is_not_read_but_shown() -> None:
    # Flux keeps Ready first; a Ready further down isn't read, but its message is shown
    obj = {"status": {"conditions": [RELEASED, READY]}}
    assert not is_ready(obj)
    assert not_ready_reason(obj) == (
        "Released is True: Helm install succeeded; Ready is True: Applied revision"
    )


def test_reconciling_first_shows_the_error_in_ready() -> None:
    # while Flux retries, Reconciling comes first and Ready holds the error
    obj = {"status": {"conditions": [RECONCILING, NOT_READY]}}
    assert not is_ready(obj)
    assert not_ready_reason(obj) == (
        "Reconciling is True: Detecting drift; Ready is False: install failed"
    )
