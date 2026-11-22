"""Checks of the objects the kind test creates for the repository's roots; they need no
cluster."""

import base64

import pytest
from ci_context import MissingGPGKeyError
from repository_objects import (
    credentials_secret,
    credentials_secret_name,
    decryption_secrets,
)


def test_a_decryption_secret_holds_the_master_key() -> None:
    key = base64.b64encode(b"an armoured private key").decode()
    assert decryption_secrets([("default", "golem-master")], key) == [
        {
            "metadata": {"name": "golem-master", "namespace": "default"},
            "type": "Opaque",
            "data": {"master.asc": key},
        }
    ]


def test_no_decryption_secret_needs_no_key() -> None:
    # ESO only: no root decrypts, so an empty GITOPS_MASTER_GPG_KEY is fine
    assert decryption_secrets([], "") == []


def test_a_root_that_decrypts_needs_the_key() -> None:
    with pytest.raises(MissingGPGKeyError):
        decryption_secrets([("default", "sops-gpg-master")], "")


def test_credentials_for_a_private_repository() -> None:
    token = "not-a-token"  # nosec B105 - a stand-in
    secret = credentials_secret(("default", "gitops"), token)
    assert secret == {
        "metadata": {"name": credentials_secret_name("gitops"), "namespace": "default"},
        "type": "Opaque",
        "stringData": {"username": "x-access-token", "password": token},
    }
    assert credentials_secret_name("gitops") == "gitops-kind-test-credentials"
