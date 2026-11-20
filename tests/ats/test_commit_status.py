"""Checks of how commit_status suspends the Alert and judges the Receiver and the tokens; they
need no cluster."""

import base64

from commit_status import receiver_problems, suspended, suspended_alerts, token_problems

READY = {"conditions": [{"type": "Ready", "status": "True"}]}


def test_suspended_sets_suspend() -> None:
    alert = {"metadata": {"name": "a"}, "spec": {"eventSeverity": "info"}}
    assert suspended(alert) == {
        "metadata": {"name": "a"},
        "spec": {"eventSeverity": "info", "suspend": True},
    }
    # the manifest read from the repository stays as it is
    assert "suspend" not in alert["spec"]


def test_suspended_alerts_of_a_build() -> None:
    # the organisation's build holds its Alert among other objects
    alert = {"kind": "Alert", "metadata": {"name": "a"}, "spec": {}}
    provider = {"kind": "Provider", "metadata": {"name": "p"}, "spec": {}}
    assert suspended_alerts([provider, alert, None]) == [
        {"kind": "Alert", "metadata": {"name": "a"}, "spec": {"suspend": True}}
    ]


def test_suspended_alerts_none() -> None:
    assert suspended_alerts([{"kind": "Provider", "spec": {}}]) == []


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


def _secret(data: dict | None) -> dict:
    return {"data": data}


def test_token_problems_expected_value() -> None:
    encoded = base64.b64encode(b"from-the-store").decode()
    assert (
        token_problems("default/t", _secret({"token": encoded}), "from-the-store") == []
    )


def test_token_problems_missing_secret() -> None:
    assert token_problems("default/t", None, "from-the-store") == [
        "Secret 'default/t' isn't there"
    ]


def test_token_problems_no_token() -> None:
    other = base64.b64encode(b"from-the-store").decode()
    assert token_problems("default/t", _secret({"other": other}), "from-the-store") == [
        "Secret 'default/t' has no 'token'"
    ]
    assert token_problems("default/t", _secret(None), "from-the-store") == [
        "Secret 'default/t' has no 'token'"
    ]


def test_token_problems_other_value() -> None:
    encoded = base64.b64encode(b"x").decode()
    assert token_problems(
        "default/t", _secret({"token": encoded}), "from-the-store"
    ) == ["Secret 'default/t' has another 'token' than the store's"]
