"""Pins the list, in the organisation's kustomization.yaml, of the files that name the
organisation through the placeholders its replacements complete: a customer who doesn't use
the replacements edits those files instead. Needs no cluster."""

import re
from collections.abc import Iterator
from pathlib import Path

import yaml

ORG_DIR = (
    Path(__file__).resolve().parent
    / "../../management-clusters/MC_NAME/organizations/ORG_NAME"
).resolve()
# a file in the list: `#   - path`, relative to the organisation's directory
LISTED = re.compile(r"^\s*#\s+- (\S+\.yaml)\s*$")


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, str):
        yield value


def names_the_organisation(text: str) -> bool:
    """Whether a value in the YAML documents `text` is a placeholder for the organisation:
    `ORG_NAME`, or a name with `org-ORG_NAME` in it. Paths that name the `ORG_NAME`
    directory don't count."""
    return any(
        s == "ORG_NAME" or "org-ORG_NAME" in s
        for doc in yaml.safe_load_all(text)
        for s in _strings(doc)
    )


def listed_files(kustomization: str) -> set[str]:
    return {
        m.group(1) for line in kustomization.splitlines() if (m := LISTED.match(line))
    }


def test_names_the_organisation() -> None:
    assert names_the_organisation('a: {b: ["ORG_NAME"]}')
    assert names_the_organisation("metadata: {namespace: org-ORG_NAME}")
    assert not names_the_organisation(
        "path: ./organizations/ORG_NAME/workload-clusters"
    )
    assert not names_the_organisation("# org-ORG_NAME in a comment\na: b")


def test_listed_files() -> None:
    assert listed_files("#   - a/b.yaml\n# other\n  #   - c.yaml\nx: y") == {
        "a/b.yaml",
        "c.yaml",
    }


def test_kustomization_lists_every_file_that_names_the_organisation() -> None:
    kustomization = ORG_DIR / "kustomization.yaml"
    naming = {
        str(f.relative_to(ORG_DIR))
        for f in ORG_DIR.rglob("*.yaml")
        if f != kustomization and names_the_organisation(f.read_text())
    }
    assert naming, "no file names the organisation through a placeholder"
    assert listed_files(kustomization.read_text()) == naming
