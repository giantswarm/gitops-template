"""Checks of how the Secret the PushSecret example writes into the workload cluster is judged;
they need no cluster."""

import base64

from workload_cluster_secret_push import (
    PASSWORD_LENGTH,
    PUSHED_KEY,
    pushed_secret_problems,
)


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
