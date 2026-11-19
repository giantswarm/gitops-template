"""Chainsaw runs the YAML tests in tests/chainsaw against the kind cluster.

The shared workflow creates the kind cluster and runs only this pytest suite on it, so the
suite runs Chainsaw itself: it downloads the pinned release, checks its checksum and runs the
tests with the names of the template's examples, in tests/chainsaw/values.yaml.
test_flux_objects.py runs it once everything the tests look at is ready.
"""

import hashlib
import io
import tarfile
from pathlib import Path

import requests
from conftest import run_tool

# renovate: datasource=github-releases depName=kyverno/chainsaw
CHAINSAW_VERSION = "v0.2.15"
# The checksum of the release's chainsaw_linux_amd64.tar.gz, from its checksums.txt. Renovate
#  doesn't update it: when it moves the version, the kind test fails with a checksum mismatch
#  until the checksum of the new release is set here, too.
CHAINSAW_SHA256 = "295d226c89f126c0a97775d364be149f47a810c8a3f9829ee410583d0c1abe3c"
CHAINSAW_URL = (
    "https://github.com/kyverno/chainsaw/releases/download/"
    f"{CHAINSAW_VERSION}/chainsaw_linux_amd64.tar.gz"
)
DOWNLOAD_TIMEOUT_SEC = 60

TESTS_DIR = Path(__file__).resolve().parent.parent / "chainsaw"
VALUES_FILE = TESTS_DIR / "values.yaml"


class ChecksumError(Exception):
    """The download isn't the archive CHAINSAW_SHA256 pins."""

    def __init__(self, url: str) -> None:
        super().__init__(f"Checksum mismatch for '{url}'.")


def download(url: str) -> bytes:
    response = requests.get(url, timeout=DOWNLOAD_TIMEOUT_SEC)
    response.raise_for_status()
    return response.content


def fetch(directory: Path) -> Path:
    """Download the pinned Chainsaw into `directory` and return the path of the binary."""
    archive = download(CHAINSAW_URL)
    if hashlib.sha256(archive).hexdigest() != CHAINSAW_SHA256:
        raise ChecksumError(CHAINSAW_URL)
    binary = directory / "chainsaw"
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        member = tar.extractfile("chainsaw")
        if member is None:
            raise KeyError("chainsaw")
        binary.write_bytes(member.read())
    binary.chmod(0o755)
    return binary


def run_chainsaw(directory: Path) -> str:
    """Fetch Chainsaw into `directory` and run every test in TESTS_DIR with the kind test's
    values, against the cluster of $KUBECONFIG, and return Chainsaw's report, with each test and
    step. When a test fails, it logs the report and fails.
    """
    return run_tool(
        str(fetch(directory)),
        CHAINSAW_URL,
        "test",
        "--test-dir",
        str(TESTS_DIR),
        "--values",
        str(VALUES_FILE),
        "--no-color",
    )
