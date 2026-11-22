"""G1: which clusters gate their secondary apps, and how cluster_gate judges what Flux did,
without a cluster.

A gate is a Kustomization that health-checks a Cluster API `Cluster`, and the Kustomizations that
depend on it. The test finds them in the cluster once the organisations' Kustomizations have
applied them, so it needs no list of the repository's clusters: a fork's own clusters get their
stand-in `Cluster`s too. The base apps a cluster's Kustomization applies before the cluster is
Available are `clusterBaseApps` in kind-test.yaml.
"""

from typing import NamedTuple

from flux_inventory import DEPENDENCY_NOT_READY, inventory_keys

CLUSTER_KIND = "Cluster"


class Gate(NamedTuple):
    """A Cluster, the Kustomization that health-checks it, in the Cluster's namespace, the
    Kustomizations that depend on that one, by `namespace/name`, and the base apps the cluster's
    Kustomization applies, the HelmReleases in the Cluster's namespace."""

    namespace: str
    cluster: str
    cluster_kustomization: str
    dependents: list[str]
    base_apps: list[str]


def _depends_on(kustomization: dict, namespace: str, name: str) -> bool:
    own = kustomization["metadata"].get("namespace", "default")
    return any(
        d.get("name") == name and d.get("namespace", own) == namespace
        for d in (kustomization.get("spec") or {}).get("dependsOn") or []
    )


def gates_in_cluster(
    kustomizations: dict[str, dict], base_apps: dict[str, list[str]]
) -> list[Gate]:
    """The gates of `kustomizations`, by `namespace/name`, sorted by Cluster, with the base apps
    of `base_apps`, by the Cluster's `namespace/name`."""
    gates = []
    for k in kustomizations.values():
        namespace = k["metadata"].get("namespace", "default")
        name = k["metadata"]["name"]
        for check in (k.get("spec") or {}).get("healthChecks") or []:
            if check.get("kind") != CLUSTER_KIND:
                continue
            cluster_namespace = check.get("namespace", namespace)
            gates.append(
                Gate(
                    cluster_namespace,
                    check["name"],
                    name,
                    sorted(
                        key
                        for key, d in kustomizations.items()
                        if _depends_on(d, namespace, name)
                    ),
                    base_apps.get(f"{cluster_namespace}/{check['name']}", []),
                )
            )
    return sorted(gates, key=lambda g: (g.namespace, g.cluster))


OWNER_LABEL = "kustomize.toolkit.fluxcd.io/name"


def ready_condition(obj: dict) -> dict:
    conditions = (obj.get("status") or {}).get("conditions") or []
    return next((c for c in conditions if c.get("type") == "Ready"), {})


def held_problems(key: str, obj: dict | None) -> list[str]:
    """Why the Kustomization `key` isn't waiting for its cluster, if it isn't."""
    if obj is None:
        return [f"Kustomization '{key}' doesn't exist"]
    problems = []
    ready = ready_condition(obj)
    if ready.get("reason") != DEPENDENCY_NOT_READY:
        problems.append(
            f"Kustomization '{key}' isn't waiting for its dependency: "
            f"Ready is {ready.get('status')}, {ready.get('reason')}"
        )
    applied = sorted(inventory_keys(obj))
    if applied:
        problems.append(
            f"Kustomization '{key}' applied {applied} before the cluster was Available"
        )
    return problems


def opened_problems(key: str, obj: dict | None) -> list[str]:
    """Why the Kustomization `key` isn't ready once its cluster is, if it isn't."""
    if obj is None:
        return [f"Kustomization '{key}' doesn't exist"]
    ready = ready_condition(obj)
    if ready.get("status") == "True":
        return []
    return [
        f"Kustomization '{key}' isn't ready after the cluster was Available: "
        f"{ready.get('reason')}: {ready.get('message', '')}"
    ]


def base_app_problems(gate: Gate, hrs: dict[str, dict]) -> list[str]:
    """Why the base apps of `gate`, among the HelmReleases `hrs` by `namespace/name`, aren't
    applied by the cluster's Kustomization, if they aren't."""
    problems = []
    for name in gate.base_apps:
        key = f"{gate.namespace}/{name}"
        labels = (hrs.get(key) or {}).get("metadata", {}).get("labels") or {}
        owner = labels.get(OWNER_LABEL)
        if owner != gate.cluster_kustomization:
            problems.append(
                f"base app HelmRelease '{key}' isn't applied by "
                f"'{gate.cluster_kustomization}' while the cluster isn't Available: "
                f"its owner is {owner}"
            )
    return problems
