"""G1: a cluster's apps install once the cluster is ready.

A cluster with apps has a cluster Kustomization, whose health check waits for the cluster's
Cluster API `Cluster` to be Available, and Kustomizations for its apps and app sets that depend on
it. The test cluster runs no Cluster API controllers, so the check creates a stand-in `Cluster`
for each such cluster, with Available False, and the apps Kustomizations have to wait for their
dependency without applying anything. Then it sets Available True, and they have to get ready.

test_flux_objects.py runs the check before the Kustomizations are checked, as they can't get ready
until the stand-ins are Available.
"""

import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

import pykube
from checks import waits
from conftest import FLUX_OBJECTS_NAMESPACE
from flux_inventory import inventory_keys
from pykube.objects import NamespacedAPIObject
from pytest_helm_charts.flux.kustomization import KustomizationCR


class CAPICluster(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta2"
    endpoint = "clusters"
    kind = "Cluster"


CLUSTERS_NAMESPACE = "org-org-name"
# The clusters with apps, by the name of their `Cluster`, and the Kustomizations that apply their
#  apps and app sets, which depend on the cluster's Kustomization.
GATED_KUSTOMIZATIONS: dict[str, list[str]] = {
    "capi-wc-name": ["mc-name-clusters-capi-wc-name-apps"],
    "out-of-band-flux-app": [
        "mc-name-clusters-out-of-band-flux-app-apps",
        "mc-name-clusters-out-of-band-flux-app-app-sets",
    ],
    "out-of-band-no-flux": [
        "mc-name-clusters-out-of-band-no-flux-apps",
        "mc-name-clusters-out-of-band-no-flux-app-sets",
    ],
}
# kustomize-controller's reason while a Kustomization in `dependsOn` isn't ready
DEPENDENCY_NOT_READY = "DependencyNotReady"
# The root Kustomization creates the apps Kustomizations, which then reconcile once. Once the
#  cluster is Available, they retry their dependency every 30 s, kustomize-controller's default.
GATE_TIMEOUT_SEC = 180


def available_condition(status: str) -> dict:
    """A v1beta2 `Available` condition. v1beta2 conditions require a message, even an empty one."""
    return {
        "type": "Available",
        "status": status,
        "reason": "Available" if status == "True" else "NotAvailable",
        "message": "",
        "lastTransitionTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def stand_in_cluster(api: pykube.HTTPClient, name: str) -> CAPICluster:
    """A `Cluster` no controller acts on. The schema rejects an empty `spec`."""
    return CAPICluster(
        api,
        {
            "apiVersion": CAPICluster.version,
            "kind": CAPICluster.kind,
            "metadata": {"name": name, "namespace": CLUSTERS_NAMESPACE},
            "spec": {"paused": True},
        },
    )


def set_available(cluster: CAPICluster, status: str) -> None:
    """Set the `Cluster`'s Available condition through the status subresource."""
    cluster.patch(
        {"status": {"conditions": [available_condition(status)]}},
        subresource="status",
    )


def gated_keys() -> list[str]:
    """`namespace/name` of every Kustomization that waits for a cluster."""
    return [
        f"{FLUX_OBJECTS_NAMESPACE}/{name}"
        for names in GATED_KUSTOMIZATIONS.values()
        for name in names
    ]


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


def gate_problems(
    api: pykube.HTTPClient, judge: Callable[[str, dict | None], list[str]]
) -> list[str]:
    current = waits.list_objects(api, KustomizationCR, ())
    return [p for k in gated_keys() for p in judge(k, current.get(k))]


def poll(check: Callable[[], list[str]], timeout_sec: int) -> list[str]:
    """Poll `check` until it returns no problems or `timeout_sec` is up; return the last ones."""
    deadline = time.monotonic() + timeout_sec
    while True:
        problems = check()
        if not problems or time.monotonic() >= deadline:
            return problems
        time.sleep(waits.POLL_INTERVAL_SEC)


def check_cluster_gate(clusters: Iterable[CAPICluster]) -> list[str]:
    """G1 with the stand-in `clusters`: Available False holds the apps Kustomizations, Available
    True lets them apply. Returns the problems; every cluster ends up Available either way, so
    the other checks can run."""
    clusters = list(clusters)
    api = clusters[0].api
    for cluster in clusters:
        set_available(cluster, "False")
    held = poll(lambda: gate_problems(api, held_problems), GATE_TIMEOUT_SEC)
    for cluster in clusters:
        set_available(cluster, "True")
    opened = poll(lambda: gate_problems(api, opened_problems), GATE_TIMEOUT_SEC)
    return held + opened


def stand_in_clusters(api: pykube.HTTPClient) -> list[CAPICluster]:
    """Create a stand-in `Cluster` for every cluster with apps; an existing one is reused."""
    clusters = []
    for name in GATED_KUSTOMIZATIONS:
        cluster = stand_in_cluster(api, name)
        if not cluster.exists():
            cluster.create()
        clusters.append(cluster)
    return clusters
