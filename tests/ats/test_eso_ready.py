"""Checks of how ESO's log is read when an object doesn't get Ready; they need no cluster."""

import eso_ready
import pykube
import pytest
import requests
from eso_kinds import SecretStoreCR
from eso_ready import log_lines_about, wait_ready
from workload_cluster_secret_read import NAMESPACE

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
