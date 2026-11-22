"""A pytest plugin that skips the tests that need the cluster on a pull request from a fork,
which GitHub gives none of the repository's secrets.

Without the GITOPS_MASTER_GPG_KEY secret, Flux can't decrypt the SOPS secrets, so the tests
that need the cluster can't pass. Anywhere else, including the runs in a fork itself, a missing
key is a broken setup, and repository_objects fails the tests when a root Kustomization decrypts.

The module has no asserts to rewrite, and conftest.py imports it before pytest loads it as a
plugin: PYTEST_DONT_REWRITE.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME = "GITOPS_MASTER_GPG_KEY"
# The fixture every test that needs the cluster, and so the key, depends on.
CLUSTER_TEST_FIXTURE = "gitops_test_config"
# Why the tests that need the cluster are skipped in this session, or None.
SKIP_REASON = pytest.StashKey[str | None]()


class MissingGPGKeyError(Exception):
    """The master private GPG key is empty, and a root Kustomization decrypts with it."""

    def __init__(self) -> None:
        super().__init__(
            "master gpg key missing: a root Kustomization decrypts, so the armoured private "
            f"master key, base64-encoded, has to be in '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}'"
        )


def read_event(event_path: str | None) -> dict:
    """The run's event payload from `GITHUB_EVENT_PATH`, or an empty one if it can't be read,
    such as outside GitHub Actions."""
    if not event_path:
        return {}
    try:
        with Path(event_path).open() as f:
            event = json.load(f)
    except (OSError, ValueError):
        return {}
    return event if isinstance(event, dict) else {}


def pull_request_from_fork(event: dict) -> bool:
    """Whether the `pull_request` event payload `event` is of a pull request from a repository
    other than the one it targets, a fork."""
    pull_request = event.get("pull_request")
    if not pull_request:
        return False
    # The head repository is null when the fork was deleted after the pull request was opened.
    head_repo = (pull_request.get("head") or {}).get("repo")
    base_repo = event.get("repository") or {}
    return head_repo is None or head_repo.get("full_name") != base_repo.get("full_name")


def missing_secrets_skip_reason(environ: Mapping[str, str]) -> str | None:
    """The reason to skip the tests that need the cluster, or None to run them: only a
    `pull_request` run from a fork without the key skips them."""
    if environ.get(GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME):
        return None
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return None
    if not pull_request_from_fork(read_event(environ.get("GITHUB_EVENT_PATH"))):
        return None
    return (
        "The kind test is skipped: this pull request comes from a fork, and GitHub gives pull"
        " requests from forks none of the repository's secrets, so"
        f" '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' is empty and Flux can't decrypt the SOPS"
        " secrets. The checks that need no cluster still run. The kind test runs on pull"
        " requests from a branch of the repository itself (see docs/how-to/configure-ci.md)."
    )


def skip_cluster_tests(items: list[pytest.Item], reason: str) -> None:
    """Skip the tests that need the cluster; the checks that need no cluster still run."""
    for item in items:
        if CLUSTER_TEST_FIXTURE in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_configure(config: pytest.Config) -> None:
    """Decide once per session, so the header and the skips can't disagree."""
    config.stash[SKIP_REASON] = missing_secrets_skip_reason(os.environ)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    reason = config.stash[SKIP_REASON]
    if reason:
        skip_cluster_tests(items, reason)


def pytest_report_header(config: pytest.Config) -> list[str]:
    """Say why the tests that need the cluster are skipped, if they are, as a GitHub Actions
    warning, so it shows on the run's summary page too."""
    reason = config.stash[SKIP_REASON]
    return [f"::warning title=Kind test skipped::{reason}"] if reason else []
