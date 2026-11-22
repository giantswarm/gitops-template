"""Checks of ci_scope, which decides whether a pull request needs the full CI run; they need no
cluster."""

import json
from pathlib import Path

import ci_scope
import pytest
from ci_scope import FULL, LIGHT, decide

MANIFEST = "management-clusters/MC_NAME/apps/app.yaml"
CONFIG_MAP = "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: a\ndata:\n  a: '1'\n"


def tree(root: Path, files: dict[str, str]) -> Path:
    """A checkout at `root` with `files`, path to content."""
    for path, content in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content)
    return root


def entry(path: str, status: str = "modified", previous: str | None = None) -> dict:
    """A file as GitHub's list of a pull request's files gives it."""
    file = {"filename": path, "status": status}
    if previous:
        file["previous_filename"] = previous
    return file


def scope(
    tmp_path: Path, files: list[dict], base: dict[str, str], head: dict[str, str]
) -> tuple[str, list[str]]:
    """The decision for `files`, between checkouts with `base` and `head`."""
    decision = decide(
        files,
        len(files),
        tree(tmp_path / "base", base),
        tree(tmp_path / "head", head),
    )
    return decision.scope, decision.reasons


def test_markdown_only(tmp_path: Path) -> None:
    files = [entry("README.md"), entry("docs/how-to/configure-ci.md")]
    assert scope(tmp_path, files, {}, {})[0] == LIGHT


@pytest.mark.parametrize(
    "path",
    [
        "docs/images/diagram.png",
        "renovate.json5",
        "tests/chainsaw/values.yaml",
        ".github/workflows/chainsaw.yaml",
        ".gitignore",
        "CODEOWNERS",
        "LICENSE",
        "CHANGELOG.md",
        "tools/README.md",
        # A README change that breaks test-all-ff's self-tests also fails the pre-commit hook.
        "bases/environments/stages/README.md",
        "management-clusters/MC_NAME/README.md",
    ],
)
def test_ignorable_paths(tmp_path: Path, path: str) -> None:
    assert (
        scope(tmp_path, [entry(path)], {path: "a: 1\n"}, {path: "a: 2\n"})[0] == LIGHT
    )


@pytest.mark.parametrize(
    "path",
    [
        MANIFEST,
        "tools/test-all-ff",
        "tests/ats/conftest.py",
        "tests/ats/ci_scope.py",
        ".pre-commit-config.yaml",
        ".github/workflows/validate.yaml",
        ".github/workflows/validate-light.yaml",
        # Only Markdown is ignorable below these two.
        "bases/environments/stages/kustomization.yaml",
        "management-clusters/MC_NAME/notes.txt",
    ],
)
def test_paths_the_tests_read(tmp_path: Path, path: str) -> None:
    decision, reasons = scope(
        tmp_path, [entry(path)], {path: "a: 1\n"}, {path: "a: 2\n"}
    )
    assert decision == FULL
    assert any(path in reason for reason in reasons)


def test_ignorable_yaml_with_a_flux_object(tmp_path: Path) -> None:
    """test-all-ff reads every *.yaml outside tests/ that names a Flux API."""
    path = "docs/example.yaml"
    head = {path: "apiVersion: kustomize.toolkit.fluxcd.io/v1\nkind: Kustomization\n"}
    assert scope(tmp_path, [entry(path)], {path: "a: 1\n"}, head)[0] == FULL


README = "management-clusters/MC_NAME/apps/README.md"


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (CONFIG_MAP, LIGHT),
        ("# a comment\n" + CONFIG_MAP, LIGHT),
        (CONFIG_MAP.replace("'1'", "'2'"), FULL),
    ],
)
def test_example_readme_with_a_manifest(
    tmp_path: Path, head: str, expected: str
) -> None:
    files = [entry(README), entry(MANIFEST)]
    base = {README: "a", MANIFEST: CONFIG_MAP}
    assert scope(tmp_path, files, base, {README: "b", MANIFEST: head})[0] == expected


def test_comment_only_yaml_change(tmp_path: Path) -> None:
    head = "# a new comment\n" + CONFIG_MAP.replace("'1'", '"1"  # quoted differently')
    decision, reasons = scope(
        tmp_path, [entry(MANIFEST)], {MANIFEST: CONFIG_MAP}, {MANIFEST: head}
    )
    assert decision == LIGHT
    assert reasons == [f"{MANIFEST}: same YAML content"]


def test_key_order(tmp_path: Path) -> None:
    head = "kind: ConfigMap\napiVersion: v1\nmetadata:\n  name: a\ndata:\n  a: '1'\n"
    assert (
        scope(tmp_path, [entry(MANIFEST)], {MANIFEST: CONFIG_MAP}, {MANIFEST: head})[0]
        == LIGHT
    )


@pytest.mark.parametrize(
    "head",
    [
        CONFIG_MAP.replace("'1'", "'2'"),
        # A string becomes a number.
        CONFIG_MAP.replace("'1'", "1"),
        # Same data, but kubeconform -strict rejects the duplicate key.
        CONFIG_MAP + "data:\n  a: '1'\n",
    ],
)
def test_real_yaml_change(tmp_path: Path, head: str) -> None:
    assert (
        scope(tmp_path, [entry(MANIFEST)], {MANIFEST: CONFIG_MAP}, {MANIFEST: head})[0]
        == FULL
    )


def test_truthy_spelling(tmp_path: Path) -> None:
    """YAML 1.1 reads both as true, the YAML 1.2 parser of kustomize reads `yes` as a string."""
    base = CONFIG_MAP.replace("'1'", "true")
    head = CONFIG_MAP.replace("'1'", "yes")
    assert (
        scope(tmp_path, [entry(MANIFEST)], {MANIFEST: base}, {MANIFEST: head})[0]
        == FULL
    )


@pytest.mark.parametrize(
    "file",
    [
        entry(MANIFEST, "added"),
        entry(MANIFEST, "removed"),
        entry("management-clusters/MC_NAME/apps/b.yaml", "renamed", MANIFEST),
        # Renamed into an ignorable path: the manifest is gone.
        entry("docs/app.yaml", "renamed", MANIFEST),
    ],
)
def test_added_removed_renamed(tmp_path: Path, file: dict) -> None:
    files = {
        MANIFEST: CONFIG_MAP,
        "management-clusters/MC_NAME/apps/b.yaml": CONFIG_MAP,
    }
    assert scope(tmp_path, [file], files, files)[0] == FULL


def test_renamed_within_ignorable_paths(tmp_path: Path) -> None:
    file = entry("docs/b.md", "renamed", "docs/a.md")
    assert scope(tmp_path, [file], {"docs/a.md": "a"}, {"docs/b.md": "a"})[0] == LIGHT


def test_unparseable_yaml(tmp_path: Path) -> None:
    head = CONFIG_MAP + "  : [\n"
    decision, reasons = scope(
        tmp_path, [entry(MANIFEST)], {MANIFEST: CONFIG_MAP}, {MANIFEST: head}
    )
    assert decision == FULL
    assert MANIFEST in reasons[0]


def test_multi_document_files(tmp_path: Path) -> None:
    other = CONFIG_MAP.replace("name: a", "name: b")
    base = {MANIFEST: CONFIG_MAP + "---\n" + other}
    commented = {MANIFEST: CONFIG_MAP + "--- # the second one\n" + other}
    swapped = {MANIFEST: other + "---\n" + CONFIG_MAP}
    extra = {MANIFEST: CONFIG_MAP + "---\n" + other + "---\n" + other}
    assert scope(tmp_path / "1", [entry(MANIFEST)], base, commented)[0] == LIGHT
    assert scope(tmp_path / "2", [entry(MANIFEST)], base, swapped)[0] == FULL
    assert scope(tmp_path / "3", [entry(MANIFEST)], base, extra)[0] == FULL


def test_list_order(tmp_path: Path) -> None:
    base = {MANIFEST: "resources:\n- a.yaml\n- b.yaml\n"}
    head = {MANIFEST: "resources:\n- b.yaml\n- a.yaml\n"}
    assert scope(tmp_path, [entry(MANIFEST)], base, head)[0] == FULL


def test_mixed_pull_request(tmp_path: Path) -> None:
    files = [entry("docs/a.md"), entry("renovate.json5"), entry(MANIFEST)]
    base = {MANIFEST: CONFIG_MAP}
    head = {MANIFEST: CONFIG_MAP.replace("'1'", "'2'")}
    decision, reasons = scope(tmp_path, files, base, head)
    assert decision == FULL
    assert len(reasons) == len(files)


def test_truncated_file_list(tmp_path: Path) -> None:
    decision = decide([entry("docs/a.md")], 3001, tmp_path, tmp_path)
    assert decision.scope == FULL


def test_no_files(tmp_path: Path) -> None:
    assert decide([], 0, tmp_path, tmp_path).scope == FULL


def test_error_means_full(tmp_path: Path) -> None:
    decision = ci_scope.main(
        ["--files", str(tmp_path / "missing.json"), "--changed", "1"]
    )
    assert decision.scope == FULL


def test_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI reads GitHub's pages of files and writes the scope and the reasons for the job."""
    files = tmp_path / "files.json"
    files.write_text(json.dumps([[entry("docs/a.md")], [entry(MANIFEST)]]))
    tree(tmp_path / "base", {MANIFEST: CONFIG_MAP})
    tree(tmp_path / "head", {MANIFEST: "# comment\n" + CONFIG_MAP})
    output, summary = tmp_path / "output", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    args = ["--files", str(files), "--changed", "2"]
    args += ["--base", str(tmp_path / "base"), "--head", str(tmp_path / "head")]
    assert ci_scope.main(args).scope == LIGHT
    assert output.read_text() == "scope=light\n"
    assert "docs/a.md" in summary.read_text()
    assert MANIFEST in summary.read_text()
