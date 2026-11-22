"""Checks of the master GPG key and of when the kind test is skipped: on a pull request from a
fork, which gets no secrets. They need no cluster."""

import json
from pathlib import Path
from types import SimpleNamespace

import ci_context
import conftest
import pytest
from ci_context import GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME as KEY

UPSTREAM = {"full_name": "giantswarm/gitops-template"}
FORK = {"full_name": "someone/gitops-template"}
NO_PR = {"push": "no pull request"}


def event_env(tmp_path: Path, name: str, head: dict | None = NO_PR) -> dict:
    """The environment of a run for event `name` in the upstream repository, from a pull
    request from `head` unless it's NO_PR, without the key. The head repository is null when
    the fork was deleted after the pull request was opened."""
    event: dict = {"repository": UPSTREAM}
    if head is not NO_PR:
        event["pull_request"] = {"head": {"repo": head}}
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event))
    return {"GITHUB_EVENT_NAME": name, "GITHUB_EVENT_PATH": str(path), KEY: ""}


@pytest.mark.parametrize(
    ("name", "head", "skipped"),
    [
        # a pull request from a fork, or from a fork deleted since: GitHub gives it no secrets
        ("pull_request", FORK, True),
        ("pull_request", None, True),
        # a pull request from a branch of the repository, which gets the secrets
        ("pull_request", UPSTREAM, False),
        # pull_request_target gets the secrets, from a fork too
        ("pull_request_target", FORK, False),
        # a push, also in a fork: a missing key is a broken setup
        ("push", NO_PR, False),
    ],
)
def test_skip_only_on_pull_requests_from_forks(
    tmp_path: Path, name: str, head: dict | None, skipped: bool
) -> None:
    """Only a pull request from a fork, which can't see the key, skips the cluster tests."""
    reason = ci_context.missing_secrets_skip_reason(event_env(tmp_path, name, head))
    assert (reason is not None, KEY in str(reason)) == (skipped, skipped)


def test_no_skip_without_an_event(tmp_path: Path) -> None:
    """Outside GitHub Actions, or with an event file that can't be read, the tests run, so a
    missing key still fails them."""
    env = {"GITHUB_EVENT_NAME": "pull_request", KEY: ""}
    missing = {**env, "GITHUB_EVENT_PATH": str(tmp_path / "missing.json")}
    reasons = [ci_context.missing_secrets_skip_reason(e) for e in (env, missing)]
    assert reasons == [None, None]


def test_no_skip_with_the_key(tmp_path: Path) -> None:
    """With the key, the cluster tests run, on a pull request from a fork too."""
    env = {**event_env(tmp_path, "pull_request", FORK), KEY: "a2V5"}
    assert ci_context.missing_secrets_skip_reason(env) is None


def test_the_configuration_reads_the_key_without_needing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key is needed only when a root decrypts, which repository_objects checks: the
    configuration of a repository without SOPS reads an empty one."""
    env = {
        **event_env(tmp_path, "pull_request", UPSTREAM),
        "GITOPS_REPO_URL": "https://github.com/giantswarm/gitops-template",
        "GITOPS_REPO_BRANCH": "main",
        "GITOPS_FLUX_APP_VERSION": "1.12.2",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert conftest.GitOpsTestConfig().master_private_key == ""
    monkeypatch.setenv(KEY, "a2V5")
    assert conftest.GitOpsTestConfig().master_private_key == "a2V5"


def test_header_and_skips_share_one_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason is decided once per session, so a later change to the key changes neither
    the warning annotation on the run nor the skips. Only the tests that need the test
    configuration, and so the cluster and the key, are skipped; the others still run."""
    for name, value in event_env(tmp_path, "pull_request", FORK).items():
        monkeypatch.setenv(name, value)
    config = SimpleNamespace(stash=pytest.Stash())
    ci_context.pytest_configure(config)  # type: ignore[arg-type]
    monkeypatch.setenv(KEY, "a2V5")
    [warning] = ci_context.pytest_report_header(config)  # type: ignore[arg-type]
    skips: dict[str, list[pytest.MarkDecorator]] = {
        "gitops_test_config": [],
        "other": [],
    }
    items = [
        SimpleNamespace(fixturenames=[n], add_marker=s.append) for n, s in skips.items()
    ]
    ci_context.pytest_collection_modifyitems(config, items)  # type: ignore[arg-type]
    skipped = {n: [m.kwargs["reason"] in warning for m in s] for n, s in skips.items()}
    assert skipped == {"gitops_test_config": [True], "other": []}
    assert warning.startswith("::warning title=Kind test skipped::")
