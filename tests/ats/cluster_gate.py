"""G1: a cluster's secondary apps install once the cluster is ready.

A cluster with apps has two Kustomizations. The cluster's applies the cluster and its base apps,
and its health check waits for the cluster's Cluster API `Cluster` to be Available. The apps
Kustomization applies the secondary apps, and depends on the cluster's. The check sets each
stand-in `Cluster` to Available False. The base apps have to be applied all the same,
and the apps Kustomization has to wait for its dependency without applying anything. Then the
check sets Available True, and the apps Kustomization has to get ready. cluster_gates lists the
clusters and judges what Flux did; stand_in_clusters creates the `Cluster`s.

test_flux_objects.py runs the check before the Kustomizations are checked, as they can't get ready
until the stand-ins are Available.
"""

import time
from collections.abc import Callable, Iterable

import pykube
from checks import waits
from cluster_gates import (
    GATES,
    apps_key,
    base_app_problems,
    held_problems,
    opened_problems,
)
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR
from stand_in_clusters import CAPICluster, set_available

# The organisation's namespace Kustomization creates the apps Kustomizations, which then
#  reconcile once. Once the cluster is Available, they retry their dependency every 30 s,
#  kustomize-controller's default.
GATE_TIMEOUT_SEC = 180


def held_gate_problems(api: pykube.HTTPClient) -> list[str]:
    """Why a cluster that isn't Available doesn't hold back exactly its secondary apps."""
    kustomizations = waits.list_objects(api, KustomizationCR, ())
    hrs = waits.list_objects(api, HelmReleaseCR, ())
    problems = []
    for gate in GATES.values():
        key = apps_key(gate)
        problems += held_problems(key, kustomizations.get(key))
        problems += base_app_problems(gate, hrs)
    return problems


def opened_gate_problems(api: pykube.HTTPClient) -> list[str]:
    """Why an apps Kustomization isn't ready once its cluster is Available."""
    kustomizations = waits.list_objects(api, KustomizationCR, ())
    return [
        p
        for gate in GATES.values()
        for p in opened_problems(apps_key(gate), kustomizations.get(apps_key(gate)))
    ]


def poll(check: Callable[[], list[str]], timeout_sec: int) -> list[str]:
    """Poll `check` until it returns no problems or `timeout_sec` is up; return the last ones."""
    deadline = time.monotonic() + timeout_sec
    while True:
        problems = check()
        if not problems or time.monotonic() >= deadline:
            return problems
        time.sleep(waits.POLL_INTERVAL_SEC)


def check_cluster_gate(clusters: Iterable[CAPICluster]) -> list[str]:
    """G1 with the stand-in `clusters`: Available False holds back the apps Kustomizations but
    not the base apps, Available True lets the apps Kustomizations apply. Returns the problems;
    every cluster ends up Available either way, so the other checks can run."""
    clusters = list(clusters)
    api = clusters[0].api
    for cluster in clusters:
        set_available(cluster, "False")
    held = poll(lambda: held_gate_problems(api), GATE_TIMEOUT_SEC)
    for cluster in clusters:
        set_available(cluster, "True")
    opened = poll(lambda: opened_gate_problems(api), GATE_TIMEOUT_SEC)
    return held + opened
