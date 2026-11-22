"""G1: a cluster's secondary apps install once the cluster's control plane is up.

A cluster with apps has two Kustomizations. The cluster's applies the cluster and its base apps,
and its health check waits for the control plane of the cluster's Cluster API `Cluster` to be
available and reachable. The apps Kustomization applies the secondary apps, and depends on the
cluster's. Each stand-in `Cluster` has a node pool short of its minimum, so it's never Available.
The check first reports its control plane not available: the base apps have to be applied all
the same, and the apps Kustomization has to wait for its dependency without applying anything.
Then the check reports the control plane available and reachable, and the apps Kustomization has
to get ready, though the cluster still isn't Available. cluster_gates finds the gates and judges
what Flux did; stand_in_clusters creates the `Cluster`s.

test_flux_objects.py runs the check before the Kustomizations are checked, as they can't get ready
until the stand-ins' control planes are up.
"""

import time
from collections.abc import Callable, Iterable

import pykube
from checks import waits
from cluster_gates import (
    Gate,
    base_app_problems,
    gates_in_cluster,
    held_problems,
    opened_problems,
)
from kind_config import kind_test_config
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from stand_in_clusters import CAPICluster, set_control_plane

# The organisation's namespace Kustomization creates the apps Kustomizations, which then
#  reconcile once. Once the control plane is up, they retry their dependency every 30 s,
#  kustomize-controller's default.
GATE_TIMEOUT_SEC = 180


def gates(api: pykube.HTTPClient) -> list[Gate]:
    """The gates of the Kustomizations in the cluster now."""
    return gates_in_cluster(
        waits.list_objects(api, KustomizationCR, ()),
        kind_test_config().cluster_base_apps(),
    )


def held_gate_problems(api: pykube.HTTPClient, gated: list[Gate]) -> list[str]:
    """Why a cluster whose control plane isn't up doesn't hold back exactly its secondary apps."""
    kustomizations = waits.list_objects(api, KustomizationCR, ())
    hrs = waits.list_objects(api, HelmReleaseCR, ())
    problems = []
    for gate in gated:
        for key in gate.dependents:
            problems += held_problems(key, kustomizations.get(key))
        problems += base_app_problems(gate, hrs)
    return problems


def opened_gate_problems(api: pykube.HTTPClient, gated: list[Gate]) -> list[str]:
    """Why an apps Kustomization isn't ready once its cluster's control plane is up."""
    kustomizations = waits.list_objects(api, KustomizationCR, ())
    return [
        p
        for gate in gated
        for key in gate.dependents
        for p in opened_problems(key, kustomizations.get(key))
    ]


def poll(check: Callable[[], list[str]], timeout_sec: int) -> list[str]:
    """Poll `check` until it returns no problems or `timeout_sec` is up; return the last ones."""
    deadline = time.monotonic() + timeout_sec
    while True:
        problems = check()
        if not problems or time.monotonic() >= deadline:
            return problems
        time.sleep(waits.POLL_INTERVAL_SEC)


def check_cluster_gate(
    api: pykube.HTTPClient, gated: list[Gate], clusters: Iterable[CAPICluster]
) -> list[str]:
    """G1 with the stand-in `clusters` of the gates `gated`: a control plane that isn't up holds
    back the apps Kustomizations but not the base apps; once it's up, the apps Kustomizations
    apply, though a node pool is short. Returns the problems; every control plane ends up
    available and reachable either way, so the other checks can run."""
    clusters = list(clusters)
    for cluster in clusters:
        set_control_plane(cluster, "False")
    held = poll(lambda: held_gate_problems(api, gated), GATE_TIMEOUT_SEC)
    for cluster in clusters:
        set_control_plane(cluster, "True")
    opened = poll(lambda: opened_gate_problems(api, gated), GATE_TIMEOUT_SEC)
    return held + opened
