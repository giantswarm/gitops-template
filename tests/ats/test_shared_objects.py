"""Checks of how shared_objects finds and compares the copies of the shared object; they need no
cluster."""

from pathlib import Path

import yaml
from shared_objects import (
    CONFIG_MAP,
    COPY_DIR,
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


def write_organisation(organisations: Path, name: str, resources: list[str]) -> None:
    """An organisation's directory: its Organization and the kustomization.yaml that lists
    `resources`."""
    directory = organisations / name.upper()
    directory.mkdir()
    (directory / f"{name.upper()}.yaml").write_text(
        f"apiVersion: security.giantswarm.io/v1alpha1\nkind: Organization\n"
        f"metadata:\n  name: {name}\n"
    )
    (directory / "kustomization.yaml").write_text(
        yaml.safe_dump({"resources": [f"{name.upper()}.yaml", *resources]})
    )


def test_copy_namespaces_of_the_organisations_that_list_the_source(
    tmp_path: Path,
) -> None:
    write_organisation(tmp_path, "b", ["shared-objects", "workload-clusters"])
    write_organisation(tmp_path, "a", ["shared-objects"])
    # an organisation without the shared object
    write_organisation(tmp_path, "c", ["workload-clusters"])
    assert copy_namespaces(tmp_path) == ["org-a", "org-b"]


def test_copy_namespaces_of_the_example() -> None:
    # the example organisation lists the source, so Flux applies a copy into its namespace
    assert copy_namespaces(ORGANIZATIONS_DIR) == ["org-org-name"]


def test_example_copy_is_in_the_placeholder_namespace() -> None:
    # the organisation's replacements put its name in place of the placeholder
    kustomization = yaml.safe_load(
        (ORGANIZATIONS_DIR / "ORG_NAME" / COPY_DIR / "kustomization.yaml").read_text()
    )
    assert kustomization["namespace"] == "org-ORG_NAME"


def test_source_has_no_namespace() -> None:
    # each organisation's kustomization sets the namespace of its copy
    source = source_config_map()
    assert source["metadata"] == {"name": CONFIG_MAP}
    assert source["data"]
