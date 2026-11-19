"""The download of the pinned Chainsaw release and how the kind test runs it."""

import hashlib
import io
import os
import subprocess  # nosec B404 - only the CompletedProcess of a stand-in run
import tarfile
from pathlib import Path

import chainsaw
import conftest
import pytest

BINARY = b"#!/bin/sh\necho chainsaw\n"


def archive(members: dict[str, bytes]) -> bytes:
    """A .tar.gz with `members`, as the Chainsaw release has it."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_fetch_installs_the_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = archive({"LICENSE": b"licence", "chainsaw": BINARY})
    monkeypatch.setattr(chainsaw, "download", lambda url: release)
    monkeypatch.setattr(chainsaw, "CHAINSAW_SHA256", sha256(release))

    binary = chainsaw.fetch(tmp_path)

    assert binary == tmp_path / "chainsaw"
    assert binary.read_bytes() == BINARY
    assert os.access(binary, os.X_OK)


def test_fetch_refuses_another_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = archive({"chainsaw": BINARY})
    monkeypatch.setattr(chainsaw, "download", lambda url: release)
    monkeypatch.setattr(chainsaw, "CHAINSAW_SHA256", sha256(b"another archive"))

    with pytest.raises(chainsaw.ChecksumError):
        chainsaw.fetch(tmp_path)
    assert not (tmp_path / "chainsaw").exists()


def test_fetch_needs_the_binary_in_the_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = archive({"README.md": b"readme"})
    monkeypatch.setattr(chainsaw, "download", lambda url: release)
    monkeypatch.setattr(chainsaw, "CHAINSAW_SHA256", sha256(release))

    with pytest.raises(KeyError):
        chainsaw.fetch(tmp_path)


def test_the_url_names_the_pinned_version() -> None:
    assert f"/download/{chainsaw.CHAINSAW_VERSION}/" in chainsaw.CHAINSAW_URL


def test_run_chainsaw_runs_the_tests_with_the_kind_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "passed", "")

    monkeypatch.setattr(chainsaw, "fetch", lambda directory: directory / "chainsaw")
    monkeypatch.setattr(conftest.shutil, "which", lambda name: name)
    monkeypatch.setattr(conftest.subprocess, "run", run)

    assert chainsaw.run_chainsaw(tmp_path) == "passed"

    [command] = calls
    assert command[:2] == [str(tmp_path / "chainsaw"), "test"]
    assert command[command.index("--test-dir") + 1] == str(chainsaw.TESTS_DIR)
    assert command[command.index("--values") + 1] == str(chainsaw.VALUES_FILE)
    assert chainsaw.VALUES_FILE.is_file()
    assert list(chainsaw.TESTS_DIR.glob("*/chainsaw-test.yaml"))


def test_a_failure_logs_the_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Chainsaw writes its report, with the step that failed, to stdout
    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 1, "step 2 failed", "")

    monkeypatch.setattr(chainsaw, "fetch", lambda directory: directory / "chainsaw")
    monkeypatch.setattr(conftest.shutil, "which", lambda name: name)
    monkeypatch.setattr(conftest.subprocess, "run", run)

    with pytest.raises(Exception, match="failed"):
        chainsaw.run_chainsaw(tmp_path)
    assert "step 2 failed" in caplog.text
