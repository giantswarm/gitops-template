"""The kind node has room for what the tests plan in the workload cluster (#368).

The kind cluster is one node on a CI runner, so every pod of the test, including the ones the
vCluster syncs to it, takes its CPU request from the same 4 CPUs. The apps of the workload
cluster scale up after their HelmReleases are Ready: each HorizontalPodAutoscaler raises its
Deployment to minReplicas, and the values change test rolls one app out with a surge. When the
node runs out, those pods stay Pending with "Insufficient cpu", and which app loses the race
changes from run to run. This check fails instead, every time, with the numbers, as soon as
what the pods request and what the tests plan don't fit with ROOM_MARGIN_CPU to spare.
"""

import pykube
from resource_requests import (
    cpu_millicores,
    planned_cpu,
    requested_cpu,
    room_problems,
)

# millicores for the pods of Jobs, which requested_cpu leaves out, such as Kyverno's cleanup
#  CronJobs and the hooks of the apps' charts
ROOM_MARGIN_CPU = 200


def _objects(api: pykube.HTTPClient, kind: type[pykube.objects.APIObject]) -> list[dict]:
    query = kind.objects(api)
    if issubclass(kind, pykube.objects.NamespacedAPIObject):
        query = query.filter(namespace=pykube.all)
    return [o.obj for o in query]


def node_room_problems(
    api: pykube.HTTPClient, workload_cluster: pykube.HTTPClient
) -> list[str]:
    """Why the kind cluster can't take the planned scale-ups of the workload cluster's apps."""
    allocatable = sum(
        cpu_millicores(((n.get("status") or {}).get("allocatable") or {}).get("cpu", "0"))
        for n in _objects(api, pykube.Node)
    )
    planned = planned_cpu(
        _objects(workload_cluster, pykube.Deployment),
        _objects(workload_cluster, pykube.HorizontalPodAutoscaler),
    )
    return room_problems(
        allocatable,
        requested_cpu(_objects(api, pykube.Pod)),
        planned,
        ROOM_MARGIN_CPU,
    )
