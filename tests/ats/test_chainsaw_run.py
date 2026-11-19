"""How the kind test runs Chainsaw, and that it logs Chainsaw's report when a test fails."""

import subprocess  # nosec B404 - only the CompletedProcess of a stand-in run
from pathlib import Path

import chainsaw
import conftest
import pytest


def stand_in_chainsaw(
    monkeypatch: pytest.MonkeyPatch, returncode: int, report: str
) -> list[list[str]]:
    """Make run_chainsaw run a stand-in that exits with `returncode` and writes `report` to
    stdout, as Chainsaw does. Return the list the commands it runs are added to."""
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, report, "")

    monkeypatch.setattr(chainsaw, "fetch", lambda directory: directory / "chainsaw")
    monkeypatch.setattr(conftest.shutil, "which", lambda name: name)
    monkeypatch.setattr(conftest.subprocess, "run", run)
    return calls


def test_run_chainsaw_runs_the_tests_with_the_kind_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = stand_in_chainsaw(monkeypatch, 0, "passed")

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
    stand_in_chainsaw(monkeypatch, 1, "step 2 failed")

    with pytest.raises(Exception, match="failed"):
        chainsaw.run_chainsaw(tmp_path)
    assert "step 2 failed" in caplog.text

