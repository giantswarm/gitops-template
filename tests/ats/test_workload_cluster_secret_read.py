"""Checks of how the Secret read from the workload cluster through its store is judged; they
need no cluster."""

import base64

from workload_cluster_secret_read import (
    NAMESPACE,
    REMOTE_NAME,
    REMOTE_VALUE,
    synced_value_problems,
)


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
