"""Checks of how shared_objects finds and compares the copies of the shared object; they need no
cluster."""

from pathlib import Path

from shared_objects import (
    CONFIG_MAP,
    ORGANIZATIONS_DIR,
    copy_namespaces,
    copy_problems,
    source_config_map,
)

SOURCE = {"data": {"ca.crt": "pem"}}


def test_copy_problems_same_data() -> None:
    assert copy_problems(SOURCE, {"data": {"ca.crt": "pem"}}, "org-a") == []


def test_copy_problems_missing_copy() -> None:
    assert copy_problems(SOURCE, None, "org-a") == [
        f"ConfigMap '{CONFIG_MAP}' isn't in namespace 'org-a'"
    ]


def test_copy_problems_other_data() -> None:
    assert copy_problems(SOURCE, {"data": {"ca.crt": "old"}}, "org-a") == [
        f"ConfigMap 'org-a/{CONFIG_MAP}' has other data than its source"
    ]


def write_organisation(organisations: Path, name: str, kustomization: str) -> None:
    directory = organisations / name / "shared-objects"
    directory.mkdir(parents=True)
    (directory / "kustomization.yaml").write_text(kustomization)


def test_copy_namespaces_of_the_organisations_that_list_the_source(
    tmp_path: Path,
) -> None:
    write_organisation(
        tmp_path,
        "b",
        "namespace: org-b\nresources:\n  - ../../../../../bases/shared_objects\n",
    )
    write_organisation(
        tmp_path,
        "a",
        "namespace: org-a\nresources:\n  - ../../../../../bases/shared_objects\n",
    )
    # an organisation without the shared object
    (tmp_path / "c").mkdir()
    assert copy_namespaces(tmp_path) == ["org-a", "org-b"]


def test_copy_namespaces_of_the_example() -> None:
    # the example organisation lists the source, so Flux applies a copy into its namespace
    assert copy_namespaces(ORGANIZATIONS_DIR) == ["org-org-name"]


def test_source_has_no_namespace() -> None:
    # each organisation's kustomization sets the namespace of its copy
    source = source_config_map()
    assert source["metadata"] == {"name": CONFIG_MAP}
    assert source["data"]
