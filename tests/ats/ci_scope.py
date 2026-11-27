"""Whether a pull request needs the full CI run, or the light one, and why.

The full run is the shared gitops-validate workflow: pre-commit, `tools/test-all-ff validate`
and the kind test. The light run is pre-commit and the tests of tests/ats that need no cluster,
which read files as text, comments and Markdown included. A pull request gets the light run when
no file it changes can change what `validate` builds or the kind test applies:

- a file neither of them reads, one that IGNORABLE names and NOT_IGNORABLE doesn't, unless it's a
  `*.yaml` that test-all-ff reads for its Flux API, see `read_for_flux`;
- a YAML file whose parsed content is the same in both versions: only comments, whitespace,
  quoting or the order of keys changed.

Everything else counts, and so does anything this module can't be sure of: a file added,
removed or renamed, YAML that doesn't parse, a list of files GitHub cut short, or any error.

    python ci_scope.py --files files.json --changed N --base BASE_DIR --head HEAD_DIR

`files.json` is GitHub's list of the pull request's files, as `gh api --paginate --slurp`
writes it; N is the number of files GitHub says the pull request changes; BASE_DIR and HEAD_DIR
are checkouts of the merge base and of the pull request's head. It prints the scope and the
reasons, and writes them to GITHUB_OUTPUT (`scope=light` or `scope=full`) and to
GITHUB_STEP_SUMMARY when those are set. It needs PyYAML and nothing else of the kind test.
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

LIGHT = "light"
FULL = "full"

# Paths neither test reads, as fnmatch patterns where `*` also matches `/`. A fork adds its own
# here, such as a directory of notes. See docs/how-to/configure-ci.md.
IGNORABLE = (
    # Markdown, anywhere. The READMEs under bases/ and management-clusters/ are also read by
    # test-all-ff validate's self-tests of tools/check-directory-readmes, but a README change that
    # breaks those also fails the check itself, a pre-commit hook that the light run runs too. The
    # tests of tests/ats that need no cluster read some Markdown, such as
    # docs/how-to/delete-cluster.md, and the light run runs them too.
    "*.md",
    "docs/*",
    # Read by Renovate only.
    "renovate.json5",
    # Run by .github/workflows/chainsaw.yaml against a management cluster; test-all-ff leaves
    # out tests/, and tests/ats doesn't read it.
    "tests/chainsaw/*",
    # Workflows other than this run's own, see NOT_IGNORABLE.
    ".github/workflows/*",
    ".gitignore",
    "CODEOWNERS",
    "LICENSE",
)
# Paths of IGNORABLE that a test does read.
NOT_IGNORABLE = (
    # The workflows of this run, and so of what it runs.
    ".github/workflows/validate.yaml",
    ".github/workflows/validate-light.yaml",
)
# test-all-ff reads every *.yaml outside tests/ and tools/testdata/ that matches this, to find
# the Flux Kustomizations it builds, wherever the file is.
FLUX_API = re.compile(r"api.*\.fluxcd\.io")
FLUX_SCAN_SKIPS = ("tests/*", "tools/testdata/*")
YAML_SUFFIXES = (".yaml", ".yml")


@dataclass(frozen=True)
class Decision:
    """The scope of the run, and why: one reason per file, or one for the whole list."""

    scope: str
    reasons: list[str]


class DuplicateKeyError(ValueError):
    """A mapping has a key twice, which kubeconform -strict rejects."""


def matches(path: str, patterns: Sequence[str]) -> bool:
    """Whether `path` matches one of `patterns`."""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def read(root: Path, path: str) -> str | None:
    """The content of `path` in the checkout at `root`, or None if it isn't there."""
    file = root / path
    return file.read_text() if file.is_file() else None


def read_for_flux(path: str, base: Path, head: Path) -> bool:
    """Whether test-all-ff reads `path`, in either version, for a Flux Kustomization."""
    if not path.endswith(".yaml") or matches(path, FLUX_SCAN_SKIPS):
        return False
    return any(FLUX_API.search(read(root, path) or "") for root in (base, head))


def ignorable(path: str, base: Path, head: Path) -> bool:
    """Whether no test reads `path`."""
    if not matches(path, IGNORABLE) or matches(path, NOT_IGNORABLE):
        return False
    return not read_for_flux(path, base, head)


def signature(node: yaml.Node) -> tuple:
    """What a YAML node means, without its comments, style or key order. Scalars keep the tag
    YAML 1.1 resolves, so `yes` and `true` differ, as they do for YAML 1.2 parsers."""
    if isinstance(node, yaml.MappingNode):
        pairs = [(signature(key), signature(value)) for key, value in node.value]
        if len({key for key, _ in pairs}) != len(pairs):
            raise DuplicateKeyError(node.start_mark)
        return ("map", node.tag, frozenset(pairs))
    if isinstance(node, yaml.SequenceNode):
        return ("seq", node.tag, tuple(signature(item) for item in node.value))
    return ("scalar", node.tag, node.value)


def yaml_content(text: str) -> tuple:
    """The signature of every document in `text`, in order."""
    return tuple(
        signature(document)
        for document in yaml.compose_all(text, Loader=yaml.SafeLoader)
    )


def same_yaml(path: str, base: Path, head: Path) -> bool:
    """Whether `path` has the same YAML content in both checkouts; False if either is missing or
    doesn't parse."""
    old, new = read(base, path), read(head, path)
    if old is None or new is None:
        return False
    try:
        return yaml_content(old) == yaml_content(new)
    except (yaml.YAMLError, DuplicateKeyError, RecursionError):
        return False


def counts(file: dict, base: Path, head: Path) -> tuple[bool, str]:
    """Whether a changed file counts for the tests, and why."""
    path = file["filename"]
    paths = [
        path,
        *([file["previous_filename"]] if file.get("previous_filename") else []),
    ]
    if all(ignorable(each, base, head) for each in paths):
        return False, f"{path}: no test reads it"
    if file["status"] == "modified" and path.endswith(YAML_SUFFIXES):
        if same_yaml(path, base, head):
            return False, f"{path}: same YAML content"
        return True, f"{path}: YAML content changed, or doesn't parse"
    return True, f"{path}: {file['status']}, and a test may read it"


def decide(files: list[dict], changed: int, base: Path, head: Path) -> Decision:
    """The scope for a pull request that changes `files`, of `changed` in all."""
    if not files or len(files) != changed:
        return Decision(
            FULL, [f"GitHub listed {len(files)} of {changed} changed files"]
        )
    results = [counts(file, base, head) for file in files]
    scope = FULL if any(count for count, _ in results) else LIGHT
    return Decision(scope, [reason for _, reason in results])


def report(decision: Decision) -> None:
    """Print the decision, and write it for the job when it runs in GitHub Actions."""
    text = f"Scope: {decision.scope}\n" + "".join(
        f"- {reason}\n" for reason in decision.reasons
    )
    sys.stdout.write(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as file:
            file.write(f"### CI scope\n\n{text}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as file:
            file.write(f"scope={decision.scope}\n")


def load_files(path: Path) -> list[dict]:
    """GitHub's list of files, from one page or a list of pages."""
    data = json.loads(path.read_text())
    if data and all(isinstance(page, list) for page in data):
        return [file for page in data for file in page]
    return list(data)


def main(argv: Sequence[str] | None = None) -> Decision:
    """Decide, from the command line, and report; any error means the full run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", type=Path, required=True)
    parser.add_argument("--changed", type=int, required=True)
    parser.add_argument("--base", type=Path, default=Path("base"))
    parser.add_argument("--head", type=Path, default=Path("head"))
    args = parser.parse_args(argv)
    try:
        decision = decide(load_files(args.files), args.changed, args.base, args.head)
    except Exception as error:  # Any error at all means the full run.
        decision = Decision(FULL, [f"error: {error!r}"])
    report(decision)
    return decision


if __name__ == "__main__":
    main()
