"""The names of the objects in the example manifests.

A Kubernetes object name is a lowercase RFC 1123 subdomain, and the API server refuses any other.
A schema check doesn't look at names, and the test applies no directory that only a workload
cluster's own Flux pulls, so test_object_names.py checks every name in the examples.
"""

import re
from pathlib import Path

import yaml

SUBDOMAIN = re.compile(r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?")
MAX_LENGTH = 253
# what Flux substitutes, `${cluster_name}`, and what Flux Operator renders, `<< inputs.cluster >>`:
#  the examples give both valid values
PLACEHOLDER = re.compile(r"\$\{[^}]+\}|<<[^>]+>>")
# RBAC names are path segments, which may hold colons and capitals, such as `system:node`
PATH_SEGMENT_KINDS = {"ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding"}


def is_valid(name: str) -> bool:
    """Whether the API server takes `name` as the name of an object, placeholders filled in."""
    literal = PLACEHOLDER.sub("x", name)
    return len(literal) <= MAX_LENGTH and SUBDOMAIN.fullmatch(literal) is not None


def invalid_names_in(manifest: str) -> list[str]:
    """The objects of `manifest` with a name the API server refuses, as `Kind/name`."""
    invalid = []
    for doc in yaml.safe_load_all(manifest):
        if not isinstance(doc, dict) or doc.get("kind") in PATH_SEGMENT_KINDS:
            continue
        name = (doc.get("metadata") or {}).get("name")
        if isinstance(name, str) and not is_valid(name):
            invalid.append(f"{doc.get('kind')}/{name}")
    return invalid


def invalid_names(directory: Path) -> list[str]:
    """Every such object in the YAML files below `directory`, as `file: Kind/name`."""
    return [
        f"{file.relative_to(directory)}: {name}"
        for file in sorted(directory.rglob("*.yaml"))
        for name in invalid_names_in(file.read_text())
    ]
