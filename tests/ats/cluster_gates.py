"""G1: which clusters gate their secondary apps, and how cluster_gate judges what Flux did,
without a cluster."""

from typing import NamedTuple

from conftest import FLUX_OBJECTS_NAMESPACE
from flux_inventory import inventory_keys


class Gate(NamedTuple):
    """The Kustomizations of a cluster with apps, and the base apps the cluster's applies."""

    cluster_kustomization: str
    apps_kustomization: str
    # the HelmReleases of the base apps, which don't wait for the cluster
    base_apps: list[str]


CLUSTERS_NAMESPACE = "org-org-name"
# the base apps of the out-of-band clusters: the Gateway API stack of bases/apps/envoy-gateway
GATEWAY_API_STACK = ["gateway-api-crds", "envoy-gateway", "gateway-api-config"]
# the clusters with apps, by the name of their `Cluster`
GATES: dict[str, Gate] = {
    "capi-wc-name": Gate(
        "mc-name-clusters-capi-wc-name", "mc-name-clusters-capi-wc-name-apps", []
    ),
    "out-of-band-flux-app": Gate(
        "mc-name-clusters-out-of-band-flux-app",
        "mc-name-clusters-out-of-band-flux-app-apps",
        [f"out-of-band-flux-app-{app}" for app in GATEWAY_API_STACK],
    ),
    "out-of-band-no-flux": Gate(
        "mc-name-clusters-out-of-band-no-flux",
        "mc-name-clusters-out-of-band-no-flux-apps",
        [f"out-of-band-no-flux-{app}" for app in GATEWAY_API_STACK],
    ),
}
OWNER_LABEL = "kustomize.toolkit.fluxcd.io/name"
# kustomize-controller's reason while a Kustomization in `dependsOn` isn't ready
DEPENDENCY_NOT_READY = "DependencyNotReady"


def apps_key(gate: Gate) -> str:
    return f"{FLUX_OBJECTS_NAMESPACE}/{gate.apps_kustomization}"


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
        key = f"{CLUSTERS_NAMESPACE}/{name}"
        labels = (hrs.get(key) or {}).get("metadata", {}).get("labels") or {}
        owner = labels.get(OWNER_LABEL)
        if owner != gate.cluster_kustomization:
            problems.append(
                f"base app HelmRelease '{key}' isn't applied by "
                f"'{gate.cluster_kustomization}' while the cluster isn't Available: "
                f"its owner is {owner}"
            )
    return problems
