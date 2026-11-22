"""What a failed kind test of the workload cluster shows about it.

A HelmRelease that installs into the test's vCluster can stop short of Ready for reasons only the
clusters show: pods the scheduler can't place, images that can't be pulled, probes that fail.
The test log has none of that, so when a test that uses the vCluster fails, its report gets a
section with the state of both clusters: the HelmReleases that install into the vCluster, the
kind node's allocatable CPU and memory against what the pods on it request, and in the vCluster
the Helm history, Deployments, ReplicaSets, HorizontalPodAutoscalers, PodDisruptionBudgets,
Pods, events and the logs of the pods that aren't ready. See issue #368.

conftest.py loads this module as a plugin, for its pytest_runtest_makereport hook.
"""

from collections.abc import Callable, Generator
from typing import Any

import pykube
import pytest
from checks.conditions import condition_true, obj_key
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from resource_requests import node_allocation
from workload_state import (
    deployment_line,
    event_lines,
    helm_history_lines,
    helm_release_lines,
    hpa_line,
    pdb_line,
    pod_line,
    replica_set_line,
)

SECTION = "workload cluster diagnostics"
# the newest events of the workload cluster
EVENTS_LIMIT = 60
# the last lines of the log of each container of a pod that isn't ready
LOG_LINES = 20


def collect(title: str, collector: Callable[[], list[str]]) -> list[str]:
    """A titled section; a collector that fails doesn't stop the others."""
    try:
        lines = collector()
    except Exception as e:  # the diagnostics must not hide the failure
        lines = [f"couldn't collect: {type(e).__name__}: {e}"]
    return [f"== {title}", *lines]


def _all(api: pykube.HTTPClient, kind: type[pykube.objects.APIObject]) -> list[dict]:
    query = kind.objects(api)
    if issubclass(kind, pykube.objects.NamespacedAPIObject):
        query = query.filter(namespace=pykube.all)
    return [o.obj for o in query]


def _container_logs(pod: pykube.Pod) -> list[str]:
    lines = []
    for c in pod.obj["spec"].get("containers") or []:
        try:
            log = pod.logs(container=c["name"], tail_lines=LOG_LINES)
        except Exception as e:  # a container that never started has no log
            log = f"no log: {e}"
        lines += [f"-- {obj_key(pod.obj)} {c['name']}", *log.splitlines()]
    return lines


def _not_ready_logs(api: pykube.HTTPClient) -> list[str]:
    return [
        line
        for p in pykube.Pod.objects(api).filter(namespace=pykube.all)
        if p.obj.get("spec", {}).get("nodeName") and not condition_true(p.obj, "Ready")
        for line in _container_logs(p)
    ]


def host_diagnostics(api: pykube.HTTPClient) -> list[str]:
    """The HelmReleases that install into a workload cluster, and the kind node's room."""
    return collect(
        "HelmReleases that install into a workload cluster",
        lambda: [
            line
            for hr in _all(api, HelmReleaseCR)
            if (hr.get("spec") or {}).get("kubeConfig")
            for line in helm_release_lines(hr)
        ],
    ) + collect(
        "kind cluster: what the pods request against what the nodes can give",
        lambda: node_allocation(_all(api, pykube.Node), _all(api, pykube.Pod)),
    )


def workload_cluster_diagnostics(api: pykube.HTTPClient) -> list[str]:
    """The apps in the vCluster: Helm history, workloads, pods, events and logs."""

    def lines(
        kind: type[pykube.objects.APIObject], line: Callable[[dict], str]
    ) -> list[str]:
        return [line(o) for o in _all(api, kind)]

    sections: list[tuple[str, Callable[[], list[str]]]] = [
        ("Helm history", lambda: helm_history_lines(_all(api, pykube.Secret))),
        ("Deployments", lambda: lines(pykube.Deployment, deployment_line)),
        ("ReplicaSets", lambda: lines(pykube.ReplicaSet, replica_set_line)),
        (
            "HorizontalPodAutoscalers",
            lambda: lines(pykube.HorizontalPodAutoscaler, hpa_line),
        ),
        ("PodDisruptionBudgets", lambda: lines(pykube.PodDisruptionBudget, pdb_line)),
        ("Pods", lambda: lines(pykube.Pod, pod_line)),
        ("Events", lambda: event_lines(_all(api, pykube.Event), EVENTS_LIMIT)),
        ("Logs of the pods that aren't ready", lambda: _not_ready_logs(api)),
    ]
    return [
        line
        for title, collector in sections
        for line in collect(f"workload cluster: {title}", collector)
    ]


def diagnostics(host: pykube.HTTPClient | None, workload: pykube.HTTPClient) -> str:
    lines = host_diagnostics(host) if host is not None else []
    return "\n".join(lines + workload_cluster_diagnostics(workload))


def diagnostics_wanted(when: str, failed: bool, funcargs: dict[str, Any]) -> bool:
    """Only a test that uses the workload cluster and fails gets them, not its fixtures'
    errors, which every test that requests them repeats."""
    return when == "call" and failed and "workload_cluster" in funcargs


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    funcargs = getattr(item, "funcargs", {})
    if diagnostics_wanted(report.when, report.failed, funcargs):
        kube_cluster = funcargs.get("kube_cluster")
        host = kube_cluster.kube_client if kube_cluster is not None else None
        report.sections.append(
            (SECTION, diagnostics(host, funcargs["workload_cluster"]))
        )
    return report
