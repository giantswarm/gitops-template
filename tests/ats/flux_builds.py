"""What each Flux Kustomization of a management cluster applies, built as Flux builds it, without
a cluster: from the root Kustomization down through every Kustomization it applies that reads the
same repository, each with its `postBuild` variables and `targetNamespace`, and the cluster it
applies to.
"""

import json
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import NamedTuple

import yaml
from root_build import build

MANAGEMENT_CLUSTER = ""
DEFAULT_NAMESPACE = "default"
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
# what holds no Flux objects to build: tests' assertions and the tools' fixtures, as for fake-flux
_NOT_SEARCHED = {("tests",), ("tools", "testdata")}


class Owner(NamedTuple):
    """What applies an object: a Flux Kustomization, or a ResourceSet. `file` is the file that
    defines it, relative to the repository, or where it's built from when that can't be found;
    `path` is a Kustomization's `spec.path`; `via` says what applies the owner itself, when that
    isn't plain from the file."""

    kind: str
    namespace: str
    name: str
    file: str
    path: str = ""
    via: str = ""


class Applied(NamedTuple):
    """One object a Kustomization applies. `cluster` is MANAGEMENT_CLUSTER or the
    `namespace/name` of the kubeconfig Secret of the cluster a Kustomization applies to,
    `namespace` where Flux puts the object, `source` the path of the Kustomization, `owner` the
    Kustomization, and `name_in_file` the object's name before `postBuild`."""

    cluster: str
    namespace: str
    obj: dict
    source: str
    owner: Owner | None = None
    name_in_file: str = ""


def documents(path: Path) -> Iterable[dict]:
    with path.open() as f:
        yield from (d for d in yaml.safe_load_all(f) if isinstance(d, dict))


def substitute(text: str, variables: dict[str, str]) -> str:
    """`text` with the `${name}` variables of Flux's `postBuild.substitute` that `variables` has
    filled in; the others stay as they are."""
    return _VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def _substituted(obj: dict, variables: dict[str, str]) -> dict:
    return json.loads(substitute(json.dumps(obj), variables))


def _searched(file: Path, repo_dir: Path) -> bool:
    parts = file.relative_to(repo_dir).parts
    return not any(p.startswith(".") for p in parts) and not any(
        parts[: len(prefix)] == prefix for prefix in _NOT_SEARCHED
    )


@cache
def _definitions(repo_dir: Path) -> dict[tuple[str, str], tuple[str, ...]]:
    """The files of the repository that define each object, by kind and name as written."""
    found: dict[tuple[str, str], list[str]] = {}
    for file in sorted(repo_dir.rglob("*.yaml")):
        if not _searched(file, repo_dir):
            continue
        try:
            docs = list(documents(file))
        except yaml.YAMLError:
            continue
        for doc in docs:
            name = (doc.get("metadata") or {}).get("name")
            if isinstance(name, str):
                key = (str(doc.get("kind")), name)
                found.setdefault(key, []).append(str(file.relative_to(repo_dir)))
    return {k: tuple(v) for k, v in found.items()}


def defining_file(repo_dir: Path, kind: str, name: str, built_from: str) -> str:
    """The file that defines the object of `kind` named `name` before `postBuild`, found by
    those, or, when no file or several do, where it's built from."""
    files = _definitions(repo_dir.resolve()).get((kind, name), ())
    if len(files) == 1:
        return files[0]
    return f"a file that {built_from} builds"


def target_cluster(kustomization: dict) -> str:
    """The cluster `kustomization` applies to: the `namespace/name` of its kubeconfig Secret,
    which is in its own namespace, or MANAGEMENT_CLUSTER."""
    ref = (kustomization["spec"].get("kubeConfig") or {}).get("secretRef") or {}
    if not ref.get("name"):
        return MANAGEMENT_CLUSTER
    namespace = kustomization["metadata"].get("namespace", DEFAULT_NAMESPACE)
    return f"{namespace}/{ref['name']}"


def spec_path(kustomization: dict) -> str:
    return str(kustomization["spec"].get("path", "")).removeprefix("./").rstrip("/")


def applies(
    repo_dir: Path,
    kustomization: dict,
    owner: Owner,
    repository: str,
    seen: set[str],
    cluster: str | None = None,
) -> list[Applied]:
    """What `kustomization`, defined as `owner` says, applies, and what the Kustomizations among
    it that read `repository` apply in turn. `cluster` is the cluster it applies to, when its
    spec doesn't say."""
    spec = kustomization["spec"]
    path = spec_path(kustomization)
    metadata = kustomization["metadata"]
    key = f"{metadata.get('namespace')}/{metadata['name']}:{path}"
    if key in seen or not (repo_dir / path).exists():
        return []
    seen.add(key)
    variables = (spec.get("postBuild") or {}).get("substitute") or {}
    if cluster is None:
        cluster = target_cluster(kustomization)
    applied: list[Applied] = []
    for raw in build(repo_dir / path):
        obj = _substituted(raw, variables)
        namespace = (
            spec.get("targetNamespace")
            or obj.get("metadata", {}).get("namespace")
            or metadata.get("namespace", DEFAULT_NAMESPACE)
        )
        name_in_file = str((raw.get("metadata") or {}).get("name", ""))
        applied.append(Applied(cluster, namespace, obj, path, owner, name_in_file))
        if (
            obj.get("kind") == "Kustomization"
            and (obj.get("spec") or {}).get("sourceRef", {}).get("name") == repository
        ):
            obj["metadata"].setdefault("namespace", namespace)
            child = Owner(
                "Kustomization",
                obj["metadata"]["namespace"],
                obj["metadata"]["name"],
                defining_file(repo_dir, "Kustomization", name_in_file, path),
                spec_path(obj),
            )
            applied += applies(repo_dir, obj, child, repository, seen)
    return applied


def applied_objects(repo_dir: Path, root_file: Path) -> list[Applied]:
    """What the root Kustomization in `root_file` applies, and the Kustomizations below it that
    read the same repository, each built as Flux builds it, with its `postBuild` variables.
    """
    root = next(
        d for d in documents(repo_dir / root_file) if d.get("kind") == "Kustomization"
    )
    owner = Owner(
        "Kustomization",
        root["metadata"].get("namespace", DEFAULT_NAMESPACE),
        root["metadata"]["name"],
        str(root_file),
        spec_path(root),
    )
    repository = root["spec"]["sourceRef"]["name"]
    return applies(repo_dir, root, owner, repository, set())
