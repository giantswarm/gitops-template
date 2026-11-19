"""The download of the pinned Chainsaw release."""

import hashlib
import io
import os
import tarfile
from pathlib import Path

import chainsaw
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
