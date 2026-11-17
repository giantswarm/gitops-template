"""Checks of the master GPG key and of where the kind test runs: in a fork without the key,
the tests that need the cluster are skipped. They need no cluster."""

import json
from pathlib import Path
from types import SimpleNamespace

import ci_context
import conftest
import pytest

FORK = {"fork": True}
UPSTREAM = {"fork": False}
KEY = "GITOPS_MASTER_GPG_KEY"


def event_file(tmp_path: Path, repository: dict, *head: dict | None) -> str:
    """Write the event payload of a push to `repository`, or of a pull request into it from
    `head`, where GITHUB_EVENT_PATH would point, and return the path. The head repository is
    null when the fork was deleted after the pull request was opened."""
    event = {"repository": repository}
    if head:
        event["pull_request"] = {"head": {"repo": head[0]}}
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    return str(path)


@pytest.mark.parametrize(
    ("repository", "head", "expected"),
    [
        # a push or a pull request in a fork of the template
        (FORK, (), True),
        (FORK, (FORK,), True),
        # a pull request from a fork, or from a fork deleted since, into the template
        (UPSTREAM, (FORK,), True),
        (UPSTREAM, (None,), True),
        # a pull request or a push in a repository that isn't a fork
        (UPSTREAM, (UPSTREAM,), False),
        (UPSTREAM, (), False),
    ],
)
def test_running_in_fork(
    tmp_path: Path, repository: dict, head: tuple, expected: bool
) -> None:
    """A run is in a fork when its repository, or the pull request's head, is a fork."""
    event = event_file(tmp_path, repository, *head)
    assert ci_context.running_in_fork(event) is expected


def test_running_in_fork_without_an_event(tmp_path: Path) -> None:
    """Outside GitHub Actions, or with an event file that can't be read, it isn't a fork, so a
    missing key still fails the test."""
    missing = str(tmp_path / "missing.json")
    assert [ci_context.running_in_fork(p) for p in (None, missing)] == [False, False]


@pytest.mark.parametrize("env", [{KEY: ""}, {}])
def test_skip_reason_in_a_fork_without_the_key(tmp_path: Path, env: dict) -> None:
    """In a fork, an empty or unset key skips the cluster tests, and the reason names it."""
    env["GITHUB_EVENT_PATH"] = event_file(tmp_path, FORK)
    assert KEY in str(ci_context.missing_secrets_skip_reason(env))


def test_no_skip_reason_with_the_key(tmp_path: Path) -> None:
    """With the key, the cluster tests run, in a fork too, and get the key."""
    env = {"GITHUB_EVENT_PATH": event_file(tmp_path, FORK), KEY: "a2V5"}
    skip_reason = ci_context.missing_secrets_skip_reason(env)
    assert (skip_reason, ci_context.master_gpg_key(env)) == (None, "a2V5")


def test_no_skip_reason_outside_a_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside a fork, a missing key is a broken setup: the test fails, as before."""
    monkeypatch.setenv("GITHUB_EVENT_PATH", event_file(tmp_path, UPSTREAM))
    monkeypatch.setenv(KEY, "")
    assert ci_context.pytest_report_header() == []
    with pytest.raises(Exception, match="master gpg key missing"):
        conftest.GitOpsTestConfig()


def test_skip_cluster_tests() -> None:
    """Only the tests that need the test configuration, and so the cluster and the key, are
    skipped; the checks that need no cluster still run."""
    cluster_skips: list[pytest.MarkDecorator] = []
    unit_skips: list[pytest.MarkDecorator] = []
    items = [
        SimpleNamespace(
            fixturenames=["gitops_test_config"], add_marker=cluster_skips.append
        ),
        SimpleNamespace(fixturenames=["monkeypatch"], add_marker=unit_skips.append),
    ]
    ci_context.skip_cluster_tests(items, "no key")  # type: ignore[arg-type]
    skips = [(m.name, m.kwargs["reason"]) for m in cluster_skips]
    assert (skips, unit_skips) == ([("skip", "no key")], [])


def test_report_header_warns_about_the_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason shows as a warning annotation on the run, not only in the pytest output."""
    monkeypatch.setenv("GITHUB_EVENT_PATH", event_file(tmp_path, FORK))
    monkeypatch.setenv(KEY, "")
    [warning] = ci_context.pytest_report_header()
    assert warning.startswith(
        "::warning title=Kind test skipped::The kind test is skipped"
    )
    monkeypatch.setenv(KEY, "a2V5")
    assert ci_context.pytest_report_header() == []
