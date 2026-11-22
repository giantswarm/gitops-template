"""The objects the kind test creates for the roots of the repository before Flux applies them: the
Secret each root decrypts with, holding the master key, and the credentials its GitRepository
reads the repository with.

On a management cluster the master key's Secret is applied by hand once, and Flux keeps it up to
date from the repository afterwards; the test creates it the same way. The key is the one in
GITOPS_MASTER_GPG_KEY: in a fork that's the fork's own master key, so the test decrypts what
production decrypts.
"""

from ci_context import MissingGPGKeyError
from kind_config import Ref

# Flux imports every `.asc` key of the Secret
MASTER_KEY_DATA_KEY = "master.asc"
# the user a GitHub token authenticates as over HTTPS
TOKEN_USERNAME = "x-access-token"  # nosec B105 - a user name, not a password


def decryption_secrets(refs: list[Ref], key: str) -> list[dict]:
    """A Secret with the master `key`, base64-encoded as GITOPS_MASTER_GPG_KEY holds it, for each
    of `refs`. Fail when one is needed and the key is empty."""
    if refs and not key:
        raise MissingGPGKeyError
    return [
        {
            "metadata": {"name": name, "namespace": namespace},
            "type": "Opaque",
            "data": {MASTER_KEY_DATA_KEY: key},
        }
        for namespace, name in refs
    ]


def credentials_secret_name(git_repository: str) -> str:
    return f"{git_repository}-kind-test-credentials"


def credentials_secret(ref: Ref, token: str) -> dict:
    """The Secret the GitRepository `ref` reads a private repository with, from the workflow's
    token."""
    namespace, name = ref
    return {
        "metadata": {"name": credentials_secret_name(name), "namespace": namespace},
        "type": "Opaque",
        "stringData": {"username": TOKEN_USERNAME, "password": token},
    }
