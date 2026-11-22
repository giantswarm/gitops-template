"""Checks of how commit_status suspends the Alert and judges the Receiver and the tokens, and of
which event messages the example's Alerts drop; they need no cluster."""

import base64
from pathlib import Path

import pytest
import yaml
from commit_status import (
    excluded,
    receiver_problems,
    suspended,
    suspended_alerts,
    token_problems,
)
from kind_config import require_example
from notification_objects import ALERT_FILE, ORG_ALERT_FILE, organization_alerts

ALERT_FILES = (ALERT_FILE, ORG_ALERT_FILE)
ALERT_IDS = ("management-cluster", "organisation")

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


def test_organization_alerts_in_the_organisation_namespace() -> None:
    # the build of namespace/ names no namespace: Flux's targetNamespace sets it
    build = "kind: Provider\nmetadata: {name: p}\n---\nkind: Alert\nmetadata: {name: a}\nspec: {}\n"
    assert organization_alerts(build, "org-a") == [
        {
            "kind": "Alert",
            "metadata": {"name": "a", "namespace": "org-a"},
            "spec": {"suspend": True},
        }
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


# kustomize-controller v1.7.3 sends this `info` event, for the new revision, while a
#  Kustomization waits for its `dependsOn` (kustomization_controller.go:255-257); 30s is the
#  default of --requeue-dependency
DEPENDENCY_WAIT = "Dependencies do not meet ready condition, retrying in 30s"
# the controller's other event messages, which the Alerts must still forward
OTHER_MESSAGES = (
    "Reconciliation finished in 2.1s, next run in 10m0s",
    "Health check passed in 1.4s",
    "Source artifact not found, retrying in 30s",
    "Source is not ready, artifact not found, retrying in 30s",
    "New revision detected during health check, cancelling",
    "Kustomization/org-a/mc-name-clusters-a configured",
    "dependency 'default/mc-name' is not ready",
    "health check failed after 5m0s: Dependencies do not meet ready condition",
)


@pytest.mark.parametrize("alert_file", ALERT_FILES, ids=ALERT_IDS)
def test_alert_drops_the_dependency_wait(alert_file: Path) -> None:
    require_example("notifications")
    alert = yaml.safe_load(alert_file.read_text())
    assert excluded(alert, DEPENDENCY_WAIT)
    # any --requeue-dependency interval
    assert excluded(alert, "Dependencies do not meet ready condition, retrying in 1m0s")


@pytest.mark.parametrize("alert_file", ALERT_FILES, ids=ALERT_IDS)
@pytest.mark.parametrize("message", OTHER_MESSAGES)
def test_alert_forwards_everything_else(alert_file: Path, message: str) -> None:
    require_example("notifications")
    assert not excluded(yaml.safe_load(alert_file.read_text()), message)


def test_excluded_without_a_list() -> None:
    assert not excluded({"spec": {}}, DEPENDENCY_WAIT)


def test_excluded_searches_like_go() -> None:
    # notification-controller's regexp.Match finds a match anywhere in the message
    assert excluded({"spec": {"exclusionList": ["ready"]}}, DEPENDENCY_WAIT)
