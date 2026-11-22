"""Stand-in Cluster API `Cluster`s for the clusters with apps.

The test cluster has the Cluster API CRDs but no controllers, so nothing acts on a `Cluster`: the
test creates one for each cluster in cluster_gates.GATES and sets its Available condition itself.
"""

from datetime import UTC, datetime

import pykube
from cluster_gates import CLUSTERS_NAMESPACE, CONTROL_PLANE_CONDITIONS, GATES
from pykube.objects import NamespacedAPIObject


class CAPICluster(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta2"
    endpoint = "clusters"
    kind = "Cluster"


# the reasons Cluster API v1.14.4 gives each condition, when True and when False
REASONS = {
    "Available": ("Available", "NotAvailable"),
    "WorkersAvailable": ("Available", "NotAvailable"),
    "ControlPlaneAvailable": ("Available", "NotAvailable"),
    "RemoteConnectionProbe": ("ProbeSucceeded", "ProbeFailed"),
}


def condition(kind: str, status: str) -> dict:
    """A v1beta2 condition. v1beta2 conditions require a message, even an empty one."""
    succeeded, failed = REASONS[kind]
    return {
        "type": kind,
        "status": status,
        "reason": succeeded if status == "True" else failed,
        "message": "",
        "lastTransitionTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def stand_in_conditions(control_plane: str) -> list[dict]:
    """The conditions of a cluster with a node pool short of its minimum, whose control plane is
    available and reachable when `control_plane` is "True"."""
    return [
        condition("Available", "False"),
        condition("WorkersAvailable", "False"),
        *(condition(kind, control_plane) for kind in CONTROL_PLANE_CONDITIONS),
    ]


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


def set_control_plane(cluster: CAPICluster, status: str) -> None:
    """Set the `Cluster`'s conditions through the status subresource: its control plane is
    available and reachable when `status` is "True", and a node pool is short either way.
    """
    cluster.patch(
        {"status": {"conditions": stand_in_conditions(status)}},
        subresource="status",
    )


def stand_in_clusters(api: pykube.HTTPClient) -> list[CAPICluster]:
    """Create a stand-in `Cluster` for every cluster with apps; an existing one is reused."""
    clusters = []
    for name in GATES:
        cluster = stand_in_cluster(api, name)
        if not cluster.exists():
            cluster.create()
        clusters.append(cluster)
    return clusters
