"""The two routes to a Secret: a SOPS-encrypted file that kustomize-controller decrypts and applies,
and an `ExternalSecret` that External Secrets Operator writes from a secret manager.

An example that shows one Secret both ways shows two routes to the same Secret, so the two agree on
its name, namespace, type, keys and labels. Only one of them may deliver it: with both applied,
kustomize-controller and ESO overwrite each other's copy, and the Secret flaps. See
docs/explanation/secrets.md, "One Secret, one route".

A SOPS file is read without decrypting it: `sops` leaves the keys and the metadata in clear text.
"""

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import yaml
from root_build import build

DEFAULT_TYPE = "Opaque"
MANAGEMENT_CLUSTER = ""
_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# (cluster, namespace, object, source): `cluster` is MANAGEMENT_CLUSTER or the kubeconfig Secret
#  of the cluster a Kustomization applies to, `namespace` where Flux puts the object, `source` the
#  path of the Kustomization that applies it
Applied = tuple[str, str, dict, str]


class SecretShape(NamedTuple):
    """What the two copies of one Secret have to agree on. `keys` is None when they can't be known
    without the secret manager."""

    namespace: str
    name: str
    type: str
    keys: tuple[str, ...] | None
    labels: tuple[tuple[str, str], ...]


class Route(NamedTuple):
    """One route to a Secret, and the file it's in."""

    shape: SecretShape
    source: str


def is_external_secret(obj: dict) -> bool:
    return obj.get("kind") == "ExternalSecret"


def is_sops_secret(obj: dict) -> bool:
    return obj.get("kind") == "Secret" and "sops" in obj


def _labels(metadata: dict | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(((metadata or {}).get("labels") or {}).items()))


def eso_secret(es: dict) -> SecretShape:
    """The Secret ESO writes for the `ExternalSecret` `es`, as far as the manifest says."""
    spec = es.get("spec") or {}
    target = spec.get("target") or {}
    template = target.get("template") or {}
    read = {d["secretKey"] for d in spec.get("data") or []}
    templated = set(template.get("data") or {})
    if templated and template.get("mergePolicy", "Replace") == "Replace":
        keys: set[str] | None = templated
    elif spec.get("dataFrom"):
        keys = None
    else:
        keys = read | templated
    return SecretShape(
        namespace=es["metadata"].get("namespace", ""),
        name=target.get("name") or es["metadata"]["name"],
        type=template.get("type", DEFAULT_TYPE),
        keys=None if keys is None else tuple(sorted(keys)),
        labels=_labels(template.get("metadata")),
    )


def sops_secret(secret: dict) -> SecretShape:
    """The Secret in a SOPS-encrypted file, from its clear text."""
    keys = set(secret.get("data") or {}) | set(secret.get("stringData") or {})
    return SecretShape(
        namespace=secret["metadata"].get("namespace", ""),
        name=secret["metadata"]["name"],
        type=secret.get("type", DEFAULT_TYPE),
        keys=tuple(sorted(keys)),
        labels=_labels(secret["metadata"]),
    )


def shape_differences(eso: SecretShape, sops: SecretShape) -> list[str]:
    """How the Secret an `ExternalSecret` writes differs from the SOPS copy of it."""
    problems = [
        f"{field}: ExternalSecret '{getattr(eso, field)}', SOPS '{getattr(sops, field)}'"
        for field in ("namespace", "name", "type")
        if getattr(eso, field) != getattr(sops, field)
    ]
    if eso.keys is None:
        problems.append(
            "keys: ExternalSecret reads them with dataFrom, so they can't be compared"
        )
    elif eso.keys != sops.keys:
        problems.append(
            f"keys: ExternalSecret {list(eso.keys)}, SOPS {list(sops.keys or ())}"
        )
    if eso.labels != sops.labels:
        problems.append(
            f"labels: ExternalSecret {dict(eso.labels)}, SOPS {dict(sops.labels)}"
        )
    return problems


def _documents(path: Path) -> Iterable[dict]:
    with path.open() as f:
        yield from (d for d in yaml.safe_load_all(f) if isinstance(d, dict))


def example_pairs(paths: list[Path], repo_dir: Path) -> list[tuple[Route, Route]]:
    """Each Secret that `paths` show both as an `ExternalSecret` and as a SOPS file, whether a
    `kustomization.yaml` lists them or not: (the ExternalSecret's route, the SOPS file's).
    """
    files = sorted(
        {f for p in paths for f in ([p] if p.is_file() else p.rglob("*.yaml"))}
    )
    eso: dict[tuple[str, str], Route] = {}
    sops: dict[tuple[str, str], Route] = {}
    for file in files:
        source = str(file.relative_to(repo_dir))
        for doc in _documents(file):
            if is_external_secret(doc):
                shape = eso_secret(doc)
                eso[(shape.namespace, shape.name)] = Route(shape, source)
            elif is_sops_secret(doc):
                shape = sops_secret(doc)
                sops[(shape.namespace, shape.name)] = Route(shape, source)
    return [(eso[k], sops[k]) for k in sorted(eso.keys() & sops.keys())]


def substitute(text: str, variables: dict[str, str]) -> str:
    """`text` with the `${name}` variables of Flux's `postBuild.substitute` that `variables` has
    filled in; the others stay as they are."""
    return _VARIABLE.sub(lambda m: variables.get(m.group(1), m.group(0)), text)


def _substituted(obj: dict, variables: dict[str, str]) -> dict:
    return json.loads(substitute(json.dumps(obj), variables))


def _applies(
    repo_dir: Path, kustomization: dict, repository: str, seen: set[str]
) -> list[Applied]:
    """What `kustomization` applies, and what the Kustomizations among it that read
    `repository` apply in turn."""
    spec = kustomization["spec"]
    path = str(spec.get("path", "")).removeprefix("./").rstrip("/")
    metadata = kustomization["metadata"]
    key = f"{metadata.get('namespace')}/{metadata['name']}:{path}"
    if key in seen or not (repo_dir / path).exists():
        return []
    seen.add(key)
    variables = (spec.get("postBuild") or {}).get("substitute") or {}
    cluster = ((spec.get("kubeConfig") or {}).get("secretRef") or {}).get(
        "name", MANAGEMENT_CLUSTER
    )
    applied: list[Applied] = []
    for raw in build(repo_dir / path):
        obj = _substituted(raw, variables)
        namespace = (
            spec.get("targetNamespace")
            or obj.get("metadata", {}).get("namespace")
            or metadata.get("namespace", "default")
        )
        applied.append((cluster, namespace, obj, path))
        if (
            obj.get("kind") == "Kustomization"
            and (obj.get("spec") or {}).get("sourceRef", {}).get("name") == repository
        ):
            obj["metadata"].setdefault("namespace", namespace)
            applied += _applies(repo_dir, obj, repository, seen)
    return applied


def applied_objects(repo_dir: Path, root_file: Path) -> list[Applied]:
    """What the root Kustomization in `root_file` applies, and the Kustomizations below it that
    read the same repository, each built as Flux builds it, with its `postBuild` variables.
    """
    root = next(
        d for d in _documents(repo_dir / root_file) if d.get("kind") == "Kustomization"
    )
    repository = root["spec"]["sourceRef"]["name"]
    return _applies(repo_dir, root, repository, set())


def delivered_twice(applied: list[Applied]) -> list[str]:
    """The Secrets that an applied `ExternalSecret` and an applied SOPS file both deliver."""
    eso: dict[tuple[str, str, str], str] = {}
    sops: dict[tuple[str, str, str], str] = {}
    for cluster, namespace, obj, source in applied:
        if is_external_secret(obj):
            eso[(cluster, namespace, eso_secret(obj).name)] = source
        elif is_sops_secret(obj):
            sops[(cluster, namespace, obj["metadata"]["name"])] = source
    return [
        f"Secret '{namespace}/{name}' on "
        f"{'the management cluster' if not cluster else f'the cluster of {cluster}'} is "
        f"written by the ExternalSecret in {eso[k]} and by the SOPS file {sops[k]}"
        for k in sorted(eso.keys() & sops.keys())
        for cluster, namespace, name in [k]
    ]
