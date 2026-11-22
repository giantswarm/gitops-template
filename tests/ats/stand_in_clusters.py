"""Stand-in Cluster API `Cluster`s for the clusters a Kustomization waits for.

The test cluster has the Cluster API CRDs but no controllers, so nothing acts on a `Cluster`: the
test creates one for each gate cluster_gates finds, in the repository's own namespaces, and sets
its Available condition itself.
"""

from datetime import UTC, datetime

import pykube
from cluster_gates import Gate
from pykube.objects import NamespacedAPIObject


class CAPICluster(NamespacedAPIObject):
    version = "cluster.x-k8s.io/v1beta2"
    endpoint = "clusters"
    kind = "Cluster"


def available_condition(status: str) -> dict:
    """A v1beta2 `Available` condition. v1beta2 conditions require a message, even an empty one."""
    return {
        "type": "Available",
        "status": status,
        "reason": "Available" if status == "True" else "NotAvailable",
        "message": "",
        "lastTransitionTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def stand_in_cluster(api: pykube.HTTPClient, namespace: str, name: str) -> CAPICluster:
    """A `Cluster` no controller acts on. The schema rejects an empty `spec`."""
    return CAPICluster(
        api,
        {
            "apiVersion": CAPICluster.version,
            "kind": CAPICluster.kind,
            "metadata": {"name": name, "namespace": namespace},
            "spec": {"paused": True},
        },
    )


def set_available(cluster: CAPICluster, status: str) -> None:
    """Set the `Cluster`'s Available condition through the status subresource."""
    cluster.patch(
        {"status": {"conditions": [available_condition(status)]}},
        subresource="status",
    )


def stand_in_clusters(api: pykube.HTTPClient, gates: list[Gate]) -> list[CAPICluster]:
    """Create a stand-in `Cluster` for every gate; an existing one is reused."""
    clusters = []
    for gate in gates:
        cluster = stand_in_cluster(api, gate.namespace, gate.cluster)
        if not cluster.exists():
            cluster.create()
        clusters.append(cluster)
    return clusters
