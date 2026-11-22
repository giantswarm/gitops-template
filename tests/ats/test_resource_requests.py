"""Checks of what resource_requests says about the pods on a node; they need no cluster."""

import pytest
from resource_requests import (
    QuantityError,
    cpu_millicores,
    memory_bytes,
    node_allocation,
    planned_cpu,
    pod_requests,
    requested_cpu,
    room_problems,
)

MI = 1024 * 1024


def container(cpu: str, memory: str) -> dict:
    return {"resources": {"requests": {"cpu": cpu, "memory": memory}}}


def pod(
    name: str,
    phase: str,
    node: str = "",
    containers: list[dict] | None = None,
    conditions: list[dict] | None = None,
) -> dict:
    spec: dict = {"containers": containers or [container("200m", "50Mi")]}
    if node:
        spec["nodeName"] = node
    return {
        "metadata": {"name": name, "namespace": "hello-world"},
        "spec": spec,
        "status": {"phase": phase, "conditions": conditions or []},
    }


@pytest.mark.parametrize(
    ("quantity", "millicores"),
    [("100m", 100), ("1", 1000), ("0.5", 500), ("2500u", 2), ("4", 4000)],
)
def test_cpu_quantities(quantity: str, millicores: int) -> None:
    assert cpu_millicores(quantity) == millicores


@pytest.mark.parametrize(
    ("quantity", "size"),
    [
        ("64Mi", 64 * MI),
        ("1Gi", 1024 * MI),
        ("256M", 256_000_000),
        ("1024", 1024),
        ("16384Ki", 16 * MI),
    ],
)
def test_memory_quantities(quantity: str, size: int) -> None:
    assert memory_bytes(quantity) == size


def test_unknown_quantity_is_refused() -> None:
    with pytest.raises(QuantityError, match="12parsecs"):
        memory_bytes("12parsecs")


def test_pod_requests_are_the_larger_of_the_containers_and_an_init_container() -> None:
    spec = {
        "containers": [container("100m", "50Mi"), container("200m", "50Mi")],
        "initContainers": [container("500m", "10Mi")],
    }
    assert pod_requests({"spec": spec}) == (500, 100 * MI)


def test_pod_requests_add_sidecars_to_the_containers() -> None:
    sidecar = container("50m", "10Mi") | {"restartPolicy": "Always"}
    spec = {"containers": [container("100m", "50Mi")], "initContainers": [sidecar]}
    assert pod_requests({"spec": spec}) == (150, 60 * MI)


def test_pod_without_requests_requests_nothing() -> None:
    assert pod_requests({"spec": {"containers": [{"name": "c"}]}}) == (0, 0)


def test_node_allocation_counts_the_pods_that_hold_the_node() -> None:
    nodes = [
        {
            "metadata": {"name": "kind"},
            "status": {"allocatable": {"cpu": "4", "memory": "16Gi"}},
        }
    ]
    unschedulable = {
        "type": "PodScheduled",
        "status": "False",
        "reason": "Unschedulable",
        "message": "0/1 nodes are available: 1 Insufficient cpu.",
    }
    pods = [
        pod("running", "Running", "kind"),
        pod("pending-on-node", "Pending", "kind"),
        # a finished pod doesn't hold its requests any more
        pod("done", "Succeeded", "kind", [container("1", "1Gi")]),
        pod("waiting", "Pending", conditions=[unschedulable]),
    ]
    lines = node_allocation(nodes, pods)
    assert lines[0] == (
        "node kind: CPU requested 400m of 4000m allocatable (3600m free), "
        "memory requested 100Mi of 16384Mi allocatable"
    )
    assert "  hello-world/running: 200m CPU, 50Mi memory" in lines
    assert not any("done" in line for line in lines)
    assert lines[-1] == (
        "unscheduled hello-world/waiting: requests 200m CPU, 50Mi memory: "
        "Unschedulable: 0/1 nodes are available: 1 Insufficient cpu."
    )


def deployment(name: str, replicas: int, cpu: str, max_surge: object = None) -> dict:
    spec: dict = {
        "replicas": replicas,
        "template": {"spec": {"containers": [container(cpu, "50Mi")]}},
    }
    if max_surge is not None:
        spec["strategy"] = {"rollingUpdate": {"maxSurge": max_surge}}
    return {"metadata": {"name": name, "namespace": "hello-world"}, "spec": spec}


def hpa(target: str, min_replicas: int) -> dict:
    return {
        "metadata": {"name": target, "namespace": "hello-world"},
        "spec": {
            "minReplicas": min_replicas,
            "scaleTargetRef": {"kind": "Deployment", "name": target},
        },
    }


def test_requested_cpu_counts_pending_pods_but_not_jobs_or_finished_ones() -> None:
    job_pod = pod("job", "Running", "kind")
    job_pod["metadata"]["ownerReferences"] = [{"kind": "Job", "name": "j"}]
    pods = [
        pod("running", "Running", "kind"),
        pod("unscheduled", "Pending"),
        pod("done", "Succeeded", "kind"),
        job_pod,
    ]
    assert requested_cpu(pods) == 400


def test_planned_cpu_is_every_scale_up_to_minreplicas_and_the_largest_surge() -> None:
    deployments = [
        # the HPA's minReplicas is 4: three more pods, and a surge of one when it rolls
        deployment("hello-world", 1, "200m", max_surge=1),
        # the default surge of 25% of 2 replicas rounds up to one pod
        deployment("envoy", 2, "110m"),
        # without an HPA it keeps its replicas
        deployment("podinfo", 1, "100m", max_surge="50%"),
    ]
    planned = planned_cpu(deployments, [hpa("hello-world", 4), hpa("other", 9)])
    assert planned == [
        ("scale hello-world/hello-world from 1 to 4 replicas", 600),
        ("roll out hello-world/hello-world with 1 more pod", 200),
    ]


def test_room_problems_name_the_numbers() -> None:
    planned = [("scale hello-world/hello-world from 1 to 4 replicas", 600)]
    assert room_problems(4000, 3585, planned, margin=200) == [
        "the kind node can't take what the tests plan: 3585m CPU requested + 600m "
        "planned + 200m margin = 4385m, more than the 4000m allocatable",
        "  scale hello-world/hello-world from 1 to 4 replicas: 600m",
    ]
    assert room_problems(4000, 2775, planned, margin=200) == []
