"""What a management cluster's root Kustomization, such as the template's `mc-name-gitops`,
applies, and what each organisation's namespace Kustomization applies, built as Flux builds them,
without a cluster.

The root applies only Organizations and objects in `default`, so its first reconcile on a new
management cluster passes Flux's dry-run and creates the Organizations. Everything in an
organisation's namespace is applied by the organisation's own Kustomization, the one with the
label ORGANIZATION_NAMESPACE_LABEL, which fails until organization-operator has created the
namespace and then succeeds on its next retry.
"""

from pathlib import Path

import yaml
from conftest import run_tool

REPO_DIR = Path(__file__).resolve().parents[2]
ORGANIZATION_NAMESPACE_LABEL = "giantswarm.io/organization-namespace"
DEFAULT_NAMESPACE = "default"
# the cluster-scoped kinds a customer may create on a management cluster
CLUSTER_SCOPED_KINDS = {"Organization"}
KUBECTL_URL = "https://kubernetes.io/docs/tasks/tools/"
KUSTOMIZATION_FILE = "kustomization.yaml"


def generated_resources(directory: Path) -> list[Path]:
    """What Flux builds from `directory` when it has no kustomization.yaml: its YAML files, and
    below it every directory with a kustomization.yaml, built whole, or, failing that, its YAML
    files."""
    if (directory / KUSTOMIZATION_FILE).is_file():
        return [directory]
    files = sorted(
        p for p in directory.iterdir() if p.is_file() and p.suffix == ".yaml"
    )
    for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
        files += generated_resources(sub)
    return files


def build(directory: Path) -> list[dict]:
    """The objects Flux builds from `directory`, before `postBuild` and `targetNamespace`."""
    objects: list[dict] = []
    for resource in generated_resources(directory):
        if resource.is_dir():
            text = run_tool(
                "kubectl",
                KUBECTL_URL,
                "kustomize",
                "--load-restrictor=LoadRestrictionsNone",
                str(resource),
            )
        else:
            text = resource.read_text()
        objects += [doc for doc in yaml.safe_load_all(text) if doc]
    return objects


def describe(obj: dict) -> str:
    metadata = obj.get("metadata") or {}
    namespace = metadata.get("namespace")
    where = f"{namespace}/" if namespace else ""
    return f"{obj.get('kind')} '{where}{metadata.get('name')}'"


def misplaced_objects(objects: list[dict]) -> list[str]:
    """The objects that are neither in `default` nor of a cluster-scoped kind a customer may
    create."""
    misplaced = []
    for obj in objects:
        namespace = (obj.get("metadata") or {}).get("namespace")
        if namespace == DEFAULT_NAMESPACE:
            continue
        if namespace is None and obj.get("kind") in CLUSTER_SCOPED_KINDS:
            continue
        misplaced.append(describe(obj))
    return misplaced


def _labelled(obj: dict) -> bool:
    labels = (obj.get("metadata") or {}).get("labels") or {}
    return (
        obj.get("kind") == "Kustomization"
        and labels.get(ORGANIZATION_NAMESPACE_LABEL) == "true"
    )


def organization_namespace_problems(objects: list[dict]) -> list[str]:
    """Why the namespace Kustomizations in `objects` don't apply into `org-<organization>` of an
    Organization of the build, if they don't."""
    organizations = {
        o["metadata"]["name"] for o in objects if o.get("kind") == "Organization"
    }
    kustomizations = [o for o in objects if _labelled(o)]
    if not kustomizations and not organizations:
        return []
    if not kustomizations:
        return [
            f"No Kustomization with the label '{ORGANIZATION_NAMESPACE_LABEL}' in the build"
        ]
    problems = []
    for k in kustomizations:
        key = describe(k).removeprefix("Kustomization ")
        organization = k["spec"]["postBuild"]["substitute"]["organization"]
        expected = f"org-{organization}"
        target = k["spec"].get("targetNamespace")
        if organization not in organizations:
            problems.append(
                f"Kustomization {key} applies the namespace of '{organization}', "
                "which has no Organization in the build"
            )
        elif target != expected:
            problems.append(
                f"Kustomization {key} applies into '{target}', not into '{expected}'"
            )
    return problems


def namespace_build_problems(objects: list[dict], namespace: str) -> list[str]:
    """The objects of an organisation's namespace/ build that name a namespace other than its
    own, `namespace`. `targetNamespace` puts the others there; an encrypted Secret names it.
    """
    return [
        describe(obj)
        for obj in objects
        if (obj.get("metadata") or {}).get("namespace") not in (None, namespace)
    ]


def root_dependency_problems(objects: list[dict], root: str) -> list[str]:
    """The namespace Kustomizations in `objects` that don't depend on the root Kustomization
    `root`, in their own namespace. With it, the root applies every commit first."""
    problems = []
    for k in (o for o in objects if _labelled(o)):
        namespace = k["metadata"].get("namespace", DEFAULT_NAMESPACE)
        depends_on = k["spec"].get("dependsOn") or []
        if not any(
            d.get("name") == root and d.get("namespace", namespace) == namespace
            for d in depends_on
        ):
            problems.append(f"{describe(k)} doesn't depend on '{root}'")
    return problems


def _kustomizations(objects: list[dict]) -> list[dict]:
    return [o for o in objects if o.get("kind") == "Kustomization"]


def source_problems(objects: list[dict], parent: dict) -> list[str]:
    """The Kustomizations of `parent`'s namespace build that read its GitRepository without
    naming the namespace it's in: a `sourceRef` without one is in the Kustomization's own
    namespace."""
    source = parent["spec"]["sourceRef"]
    namespace = source.get(
        "namespace", parent["metadata"].get("namespace", DEFAULT_NAMESPACE)
    )
    return [
        f"{describe(k)} reads {source['kind']} '{source['name']}' without "
        f"`sourceRef.namespace: {namespace}`"
        for k in _kustomizations(objects)
        if (ref := k["spec"].get("sourceRef") or {}).get("kind") == source["kind"]
        and ref.get("name") == source["name"]
        and ref.get("namespace") != namespace
    ]


def namespace_dependency_problems(objects: list[dict], parent: dict) -> list[str]:
    """The Kustomizations of `parent`'s namespace build that depend neither on `parent`, in its
    own namespace, nor on another Kustomization of the build that does."""
    name = parent["metadata"]["name"]
    namespace = parent["metadata"].get("namespace", DEFAULT_NAMESPACE)
    kustomizations = _kustomizations(objects)
    names = {k["metadata"]["name"] for k in kustomizations}
    problems = []
    for k in kustomizations:
        depends_on = k["spec"].get("dependsOn") or []
        if not any(
            (d.get("name") == name and d.get("namespace") == namespace)
            or (d.get("name") in names and "namespace" not in d)
            for d in depends_on
        ):
            problems.append(f"{describe(k)} doesn't depend on '{namespace}/{name}'")
    return problems


def decryption_problems(objects: list[dict]) -> list[str]:
    """The Kustomizations in `objects` that decrypt with a Secret the same build doesn't hold:
    `decryption.secretRef` names a Secret in the Kustomization's own namespace."""
    secrets = {o["metadata"]["name"] for o in objects if o.get("kind") == "Secret"}
    return [
        f"{describe(k)} decrypts with Secret '{ref}', which isn't in its build"
        for k in _kustomizations(objects)
        if (
            ref := ((k["spec"].get("decryption") or {}).get("secretRef") or {}).get(
                "name"
            )
        )
        and ref not in secrets
    ]


def namespace_builds(root: list[dict]) -> list[tuple[dict, list[dict]]]:
    """Each organisation's namespace Kustomization in the root build `root`, with its build."""
    return [(k, build(REPO_DIR / k["spec"]["path"])) for k in root if _labelled(k)]
