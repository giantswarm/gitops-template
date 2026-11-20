"""Checks of how ESO's log and the synced and pushed Secrets are read; they need no cluster."""

import base64

import eso_ready
import pykube
import pytest
import requests
from eso_kinds import SecretStoreCR
from eso_ready import log_lines_about, wait_ready
from workload_cluster_secret_push import (
    PASSWORD_LENGTH,
    PUSHED_KEY,
    pushed_secret_problems,
)
from workload_cluster_secret_read import (
    NAMESPACE,
    REMOTE_NAME,
    REMOTE_VALUE,
    synced_value_problems,
)

STORE = "default"
ABOUT = f'{{"msg":"x","namespace":"{NAMESPACE}","name":"{STORE}"}}'


def test_log_lines_about_the_object() -> None:
    assert log_lines_about(ABOUT, NAMESPACE, STORE) == [f"  {ABOUT}"]


def test_log_lines_about_skips_other_names_and_namespaces() -> None:
    log = "\n".join(
        [
            f'{{"name":"{STORE}","namespace":"org-other"}}',
            f'{{"name":"x{STORE}","namespace":"{NAMESPACE}"}}',
            f'{{"name":"{STORE}-auth","namespace":"{NAMESPACE}"}}',
            f'{{"msg":"remoteNamespace {STORE}","namespace":"{NAMESPACE}"}}',
        ]
    )
    assert log_lines_about(log, NAMESPACE, STORE) == []


def test_log_lines_about_keeps_the_last_three() -> None:
    log = "\n".join(f"{ABOUT} {i}" for i in range(5))
    assert log_lines_about(log, NAMESPACE, STORE) == [
        f"  {ABOUT} {i}" for i in (2, 3, 4)
    ]


class _PodWhoseLogFails:
    def logs(self, **_: object) -> str:
        raise requests.ConnectionError


class _Pods:
    def filter(self, **_: object) -> list[_PodWhoseLogFails]:
        return [_PodWhoseLogFails()]


def _not_ready(*_: object) -> None:
    pytest.fail("SecretStore isn't Ready")


def test_wait_ready_reports_the_failure_when_the_log_cant_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(eso_ready, "wait_until", _not_ready)
    monkeypatch.setattr(pykube.Pod, "objects", lambda _api: _Pods())
    with pytest.raises(pytest.fail.Exception, match="SecretStore isn't Ready"):
        wait_ready(None, SecretStoreCR, NAMESPACE, STORE, "store", 1)


def secret(value: str) -> dict:
    return {"data": {"value": base64.b64encode(value.encode()).decode()}}


def test_synced_value_problems_none_when_value_matches() -> None:
    assert synced_value_problems(secret(REMOTE_VALUE)) == []


def test_synced_value_problems_other_value() -> None:
    assert synced_value_problems(secret("stale")) == [
        f"Secret '{NAMESPACE}/{REMOTE_NAME}' doesn't hold the workload cluster's value"
    ]


def test_synced_value_problems_missing() -> None:
    assert synced_value_problems(None) == [
        f"Secret '{NAMESPACE}/{REMOTE_NAME}' doesn't exist"
    ]


def pushed(password: str) -> dict:
    return {"data": {PUSHED_KEY: base64.b64encode(password.encode()).decode()}}


def test_pushed_secret_problems_none_when_password_has_the_generators_length() -> None:
    assert pushed_secret_problems(pushed("x" * PASSWORD_LENGTH)) == []


def test_pushed_secret_problems_other_length() -> None:
    assert pushed_secret_problems(pushed("secret")) == [
        f"Secret 'default/pushed-password' has a '{PUSHED_KEY}' of 6 characters,"
        f" not {PASSWORD_LENGTH}"
    ]


def test_pushed_secret_problems_empty_key() -> None:
    assert pushed_secret_problems({"data": {PUSHED_KEY: ""}}) == [
        f"Secret 'default/pushed-password' has no '{PUSHED_KEY}'"
    ]


def test_pushed_secret_problems_missing() -> None:
    assert pushed_secret_problems(None) == [
        "Secret 'default/pushed-password' isn't in the workload cluster"
    ]
