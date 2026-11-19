"""Checks of how commit_status suspends the Alert and judges the notification objects; they
need no cluster."""

import base64

from commit_status import (
    alert_problems,
    provider_problems,
    receiver_problems,
    with_alerts_suspended,
)

PROVIDER = {
    "metadata": {"name": "github-commit-status", "namespace": "default"},
    "spec": {"type": "github", "secretRef": {"name": "github-commit-status-token"}},
}
# the Secret ESO writes, with any value under `token`
WRITTEN_SECRET = {"data": {"token": base64.b64encode(b"test").decode()}}
ALERT = {
    "metadata": {"name": "github-commit-status", "namespace": "default"},
    "spec": {"providerRef": {"name": "github-commit-status"}, "suspend": True},
}
READY = {"conditions": [{"type": "Ready", "status": "True"}]}


def test_with_alerts_suspended_adds_patch() -> None:
    root = {"kind": "Kustomization", "spec": {"path": "./x"}}
    patched = with_alerts_suspended(root)
    assert patched["spec"]["patches"] == [
        {
            "target": {"kind": "Alert"},
            "patch": '[{"op": "add", "path": "/spec/suspend", "value": true}]',
        }
    ]
    # the manifest read from the repository stays as it is
    assert "patches" not in root["spec"]


def test_with_alerts_suspended_keeps_patches() -> None:
    root = {"spec": {"patches": [{"patch": "p"}]}}
    patched = with_alerts_suspended(root)
    assert patched["spec"]["patches"][0] == {"patch": "p"}
    assert len(patched["spec"]["patches"]) == 2


def test_provider_problems_ready() -> None:
    assert provider_problems(PROVIDER, WRITTEN_SECRET) == []


def test_provider_problems_missing_provider() -> None:
    assert provider_problems(None, WRITTEN_SECRET) == ["the Provider isn't there"]


def test_provider_problems_missing_secret() -> None:
    assert provider_problems(PROVIDER, None) == [
        "Provider 'default/github-commit-status': Secret 'github-commit-status-token'"
        " isn't there"
    ]


def test_provider_problems_secret_without_token() -> None:
    assert provider_problems(PROVIDER, {"data": {"other": "eA=="}}) == [
        "Provider 'default/github-commit-status': Secret 'github-commit-status-token'"
        " has no 'token'"
    ]


def test_alert_problems_ready() -> None:
    assert alert_problems(ALERT, PROVIDER) == []


def test_alert_problems_missing_alert() -> None:
    assert alert_problems(None, PROVIDER) == ["the Alert isn't there"]


def test_alert_problems_other_provider() -> None:
    other = {**PROVIDER, "metadata": {"name": "other", "namespace": "default"}}
    assert alert_problems(ALERT, other) == [
        "Alert 'default/github-commit-status': Provider 'github-commit-status'"
        " isn't there"
    ]


def test_alert_problems_not_suspended() -> None:
    alert = {**ALERT, "spec": {"providerRef": {"name": "github-commit-status"}}}
    assert alert_problems(alert, PROVIDER) == [
        "Alert 'default/github-commit-status' isn't suspended: the test would post"
        " commit statuses to GitHub"
    ]


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
