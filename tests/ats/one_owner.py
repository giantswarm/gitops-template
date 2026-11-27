"""One owner per object: no object is applied to the same cluster by two Flux Kustomizations, or
by a Kustomization and a ResourceSet. Every Kustomization applies with the same field manager and
with `force`, so the API server never reports two of them writing one object; they take turns at
it instead. See docs/explanation/one-owner.md, "The same controller twice".

An object's identity is the cluster it's applied to, its API group and kind, its namespace and
its name, as Flux applies it: after `targetNamespace` and `postBuild`. The version doesn't count,
as the API server serves one object at every version of its kind.

Besides what each Kustomization builds, this counts:
- what a ResourceSet renders, with the entries of its own `spec.inputs` and with its own
  namespace for its provider's. An object whose name or namespace needs an input that only a
  ResourceSetInputProvider gives isn't checked, and is listed as such;
- the Kustomizations that flux-app, installed into a workload cluster by a HelmRelease, creates
  there from the `kustomizations` of its values, built from this repository at their `path`.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import yaml
from flux_builds import (
    MANAGEMENT_CLUSTER,
    Applied,
    Owner,
    applied_objects,
    applies,
    defining_file,
)
from object_names import objects_of

# The kinds of the objects that have no namespace, of those an object in this repository may be.
#  Flux leaves their namespace empty, whatever `targetNamespace` says.
CLUSTER_SCOPED_KINDS = {
    "APIService",
    "AWSClusterRoleIdentity",
    "ClusterExternalSecret",
    "ClusterPolicy",
    "ClusterRole",
    "ClusterRoleBinding",
    "ClusterSecretStore",
    "CustomResourceDefinition",
    "MutatingWebhookConfiguration",
    "Namespace",
    "Organization",
    "PersistentVolume",
    "PriorityClass",
    "StorageClass",
    "ValidatingAdmissionPolicy",
    "ValidatingAdmissionPolicyBinding",
    "ValidatingWebhookConfiguration",
}
FLUX_APP_CHART = "flux-app"
# the key of a `valuesFrom` entry without `valuesKey`
DEFAULT_VALUES_KEY = "values.yaml"
_INPUT = re.compile(r"<<\s*inputs\.([A-Za-z0-9_.]+)\s*>>")
_PROVIDER_NAMESPACE = "provider.namespace"


class Identity(NamedTuple):
    """What makes one object: `cluster` as in flux_builds.Applied, `group` empty for the core
    API group, `namespace` empty for a cluster-scoped kind."""

    cluster: str
    group: str
    kind: str
    namespace: str
    name: str


def identity(applied: Applied) -> Identity:
    obj = applied.obj
    api_version = str(obj.get("apiVersion", ""))
    group = api_version.rpartition("/")[0]
    kind = str(obj.get("kind", ""))
    namespace = "" if kind in CLUSTER_SCOPED_KINDS else applied.namespace
    return Identity(
        applied.cluster, group, kind, namespace, str(obj["metadata"].get("name"))
    )


def _owner_text(owner: Owner) -> str:
    text = f"{owner.kind} '{owner.namespace}/{owner.name}', in {owner.file}"
    if owner.path:
        text += f", spec.path {owner.path}"
    return text + (f", {owner.via}" if owner.via else "")


# ResourceSets


def _input_values(resource_set: dict, entry: dict) -> dict[str, str]:
    """The inputs of `entry` of the ResourceSet's `spec.inputs`, by the name its templates use."""
    spec = resource_set["spec"]
    permute = (spec.get("inputStrategy") or {}).get("name") == "Permute"
    prefix = resource_set["metadata"]["name"].replace("-", "_") + "." if permute else ""
    return {f"{prefix}{k}": str(v) for k, v in entry.items()}


def _render(text: str, values: dict[str, str], namespace: str) -> str:
    def value(m: re.Match) -> str:
        name = m.group(1)
        if name == _PROVIDER_NAMESPACE or name.endswith(f".{_PROVIDER_NAMESPACE}"):
            # a provider is in the ResourceSet's namespace: `inputsFrom` reads only that one
            return namespace
        return values.get(name, m.group(0))

    return _INPUT.sub(value, text)


def _rendered(applied: Applied, repo_dir: Path) -> tuple[list[Applied], list[str]]:
    """The objects the ResourceSet in `applied` renders, and what of it can't be checked."""
    resource_set = applied.obj
    namespace = applied.namespace
    name = resource_set["metadata"]["name"]
    via = ""
    if applied.owner:
        via = (
            f"applied by Kustomization '{applied.owner.namespace}/{applied.owner.name}'"
        )
    owner = Owner(
        "ResourceSet",
        namespace,
        name,
        defining_file(repo_dir, "ResourceSet", applied.name_in_file, applied.source),
        via=via,
    )
    rendered: list[Applied] = []
    unchecked: list[str] = []
    entries = (resource_set.get("spec") or {}).get("inputs") or [{}]
    for resource in objects_of(resource_set)[1:]:
        metadata = resource.get("metadata") or {}
        for entry in entries:
            values = _input_values(resource_set, entry)
            obj_name = _render(str(metadata.get("name")), values, namespace)
            obj_namespace = _render(
                str(metadata.get("namespace", namespace)), values, namespace
            )
            if "<<" in obj_name + obj_namespace:
                unchecked.append(
                    f"ResourceSet '{namespace}/{name}': {resource.get('kind')} "
                    f"'{metadata.get('name')}' has an input only Flux Operator fills in"
                )
                break
            obj = {**resource, "metadata": {**metadata, "name": obj_name}}
            rendered.append(
                Applied(applied.cluster, obj_namespace, obj, applied.source, owner)
            )
    return rendered, unchecked


# flux-app in a workload cluster


def _find(applied: list[Applied], cluster: str, kind: str, key: str) -> Applied | None:
    return next(
        (
            a
            for a in applied
            if a.cluster == cluster
            and a.obj.get("kind") == kind
            and f"{a.namespace}/{a.obj['metadata'].get('name')}" == key
        ),
        None,
    )


def _is_flux_app(release: Applied, applied: list[Applied]) -> bool:
    spec = release.obj.get("spec") or {}
    chart = ((spec.get("chart") or {}).get("spec") or {}).get("chart")
    if chart == FLUX_APP_CHART:
        return True
    ref = spec.get("chartRef") or {}
    key = f"{ref.get('namespace', release.namespace)}/{ref.get('name')}"
    source = _find(applied, release.cluster, str(ref.get("kind")), key)
    url = str(((source.obj.get("spec") or {}).get("url")) if source else "")
    return url.rstrip("/").endswith(f"/{FLUX_APP_CHART}")


def _values(release: Applied, applied: list[Applied]) -> Iterable[tuple[dict, Applied]]:
    """The values of the HelmRelease, from each `valuesFrom` ConfigMap in `applied` and from
    `spec.values`, in the order Flux merges them, with where each comes from."""
    spec = release.obj.get("spec") or {}
    for ref in spec.get("valuesFrom") or []:
        if ref.get("kind") != "ConfigMap":
            continue
        key = f"{release.namespace}/{ref.get('name')}"
        config_map = _find(applied, release.cluster, "ConfigMap", key)
        if config_map:
            text = (config_map.obj.get("data") or {}).get(
                ref.get("valuesKey", DEFAULT_VALUES_KEY)
            )
            yield yaml.safe_load(text or "") or {}, config_map
    yield spec.get("values") or {}, release


def _flux_app_kustomizations(
    release: Applied, applied: list[Applied], repo_dir: Path
) -> tuple[list[Applied], list[str]]:
    """What the Kustomizations of flux-app, installed by the HelmRelease `release`, apply in its
    workload cluster, and which of them can't be checked."""
    entries: list[dict] = []
    origin = release
    for values, source in _values(release, applied):
        if "kustomizations" in values:
            entries, origin = values["kustomizations"] or [], source
    spec = release.obj["spec"]
    secret = ((spec.get("kubeConfig") or {}).get("secretRef") or {}).get("name")
    cluster = f"{release.namespace}/{secret}" if secret else MANAGEMENT_CLUSTER
    namespace = spec.get("targetNamespace") or release.namespace
    via = (
        "of the workload cluster's Flux that HelmRelease "
        f"'{release.namespace}/{release.obj['metadata']['name']}' installs"
    )
    file = defining_file(
        repo_dir, str(origin.obj.get("kind")), origin.name_in_file, origin.source
    )
    owned: list[Applied] = []
    unchecked: list[str] = []
    for entry in entries:
        path = str(entry.get("path", "")).removeprefix("./").rstrip("/")
        owner = Owner(
            "Kustomization", namespace, str(entry.get("name")), file, path, via
        )
        if not (repo_dir / path).exists():
            unchecked.append(
                f"Kustomization '{namespace}/{owner.name}' {via}: its spec.path, {path}, "
                "isn't in this repository"
            )
            continue
        kustomization = {
            "metadata": {"name": owner.name, "namespace": namespace},
            "spec": {"path": path},
        }
        owned += applies(repo_dir, kustomization, owner, "", set(), cluster)
    return owned, unchecked


def owned_objects(repo_dir: Path, root_file: Path) -> tuple[list[Applied], list[str]]:
    """Every object the root Kustomization in `root_file` and those below it apply, what the
    ResourceSets among them render and what flux-app in a workload cluster applies, each with
    its owner; and what of it can't be checked."""
    applied = applied_objects(repo_dir, root_file)
    owned = list(applied)
    unchecked: list[str] = []
    for a in applied:
        kind = a.obj.get("kind")
        more: list[Applied] = []
        reasons: list[str] = []
        if kind == "ResourceSet":
            more, reasons = _rendered(a, repo_dir)
        elif kind == "HelmRelease" and _is_flux_app(a, applied):
            more, reasons = _flux_app_kustomizations(a, applied, repo_dir)
        owned += more
        unchecked += reasons
    return owned, unchecked


def _identity_text(i: Identity) -> str:
    kind = f"{i.kind}.{i.group}" if i.group else i.kind
    name = f"{i.namespace}/{i.name}" if i.namespace else i.name
    where = (
        "the management cluster"
        if i.cluster == MANAGEMENT_CLUSTER
        else f"the cluster of the kubeconfig Secret '{i.cluster}'"
    )
    return f"{kind} '{name}' on {where}"


def shared_objects(owned: list[Applied]) -> list[str]:
    """The objects of `owned` that more than one owner applies, each with its owners."""
    owners: dict[Identity, list[Owner]] = {}
    for a in owned:
        if a.owner is None:
            continue
        found = owners.setdefault(identity(a), [])
        if a.owner not in found:
            found.append(a.owner)
    return [
        f"{_identity_text(i)} is applied by:\n"
        + "\n".join(f"  - {_owner_text(o)}" for o in found)
        for i, found in sorted(owners.items())
        if len(found) > 1
    ]
