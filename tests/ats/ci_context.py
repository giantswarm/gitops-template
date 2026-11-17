"""The kind test's master GPG key, and where the test runs: a pytest plugin that skips the
tests that need the cluster in a fork without the GITOPS_MASTER_GPG_KEY secret.

A fork has none of the repository's secrets until its owner adds them, and GitHub never gives
a pull request from a fork the secrets of the repository it targets. Without the key, Flux
can't decrypt the SOPS secrets, so the tests that need the cluster can't pass. Anywhere else,
a missing key is a broken setup, and `master_gpg_key` fails the tests.
"""

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME = "GITOPS_MASTER_GPG_KEY"
# The fixture every test that needs the cluster, and so the key, depends on.
CLUSTER_TEST_FIXTURE = "gitops_test_config"

logger = logging.getLogger(__name__)


class MissingGPGKeyError(Exception):
    """The master private GPG key is empty."""

    def __init__(self) -> None:
        super().__init__("master gpg key missing")


def master_gpg_key(environ: Mapping[str, str]) -> str:
    """The master private GPG key from GITOPS_MASTER_GPG_KEY, which has to be set."""
    key = environ[GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME]
    if not key:
        logger.error(
            "In order to bootstrap the repository, armor-encoded master private GPG key for the"
            f" gitops repo has to be set in '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' environment"
            " variable (base64 encoded)."
        )
        raise MissingGPGKeyError
    return key


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


def running_in_fork(event_path: str | None) -> bool:
    """Whether the GitHub Actions run is in a fork, or for a pull request from one."""
    event = read_event(event_path)
    if (event.get("repository") or {}).get("fork"):
        return True
    pull_request = event.get("pull_request")
    if not pull_request:
        return False
    # The head repository is null when the fork was deleted after the pull request was opened.
    head_repo = (pull_request.get("head") or {}).get("repo")
    return head_repo is None or bool(head_repo.get("fork"))


def missing_secrets_skip_reason(environ: Mapping[str, str]) -> str | None:
    """The reason to skip the tests that need the cluster, or None to run them."""
    if environ.get(GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME):
        return None
    if not running_in_fork(environ.get("GITHUB_EVENT_PATH")):
        return None
    return (
        "The kind test is skipped: this run is in a fork, or for a pull request from one, and"
        f" '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' is empty, so Flux can't decrypt"
        " the SOPS secrets. GitHub doesn't pass secrets to pull requests from forks. To run it"
        " in your fork, add your master GPG key as its repository secret"
        f" '{GITOPS_MASTER_GPG_KEY_ENV_VAR_NAME}' (see docs/guides/ci-validation.md)."
    )


def skip_cluster_tests(items: list[pytest.Item], reason: str) -> None:
    """Skip the tests that need the cluster; the checks that need no cluster still run."""
    for item in items:
        if CLUSTER_TEST_FIXTURE in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.skip(reason=reason))


# pytest passes a hook only the arguments it names.
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    reason = missing_secrets_skip_reason(os.environ)
    if reason:
        skip_cluster_tests(items, reason)


def pytest_report_header() -> list[str]:
    """Say why the tests that need the cluster are skipped, if they are, as a GitHub Actions
    warning, so it shows on the run's summary page too."""
    reason = missing_secrets_skip_reason(os.environ)
    return [f"::warning title=Kind test skipped::{reason}"] if reason else []
