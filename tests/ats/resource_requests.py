"""What the pods on a node request against what the node can give, and why the scheduler hasn't
placed a pod. The kind cluster is one node on a CI runner, so the CPU the test's workloads request
decides whether a pod runs or stays Pending; workload_diagnostics reports it (#368)."""

import math
import re
from collections.abc import Iterable
from decimal import Decimal

from checks.conditions import obj_key

MI = 1024 * 1024
_QUANTITY = re.compile(r"^([0-9.]+)([a-zA-Z]*)$")
_CPU_UNITS = {
    "n": Decimal("1e-6"),
    "u": Decimal("1e-3"),
    "m": Decimal(1),
    "": Decimal(1000),
}
_MEMORY_UNITS = {
    "": Decimal(1),
    "k": Decimal(10**3),
    "M": Decimal(10**6),
    "G": Decimal(10**9),
    "T": Decimal(10**12),
    "Ki": Decimal(2**10),
    "Mi": Decimal(2**20),
    "Gi": Decimal(2**30),
    "Ti": Decimal(2**40),
}
# a pod in one of these phases holds no resources of its node any more
_FINISHED = ("Succeeded", "Failed")


class QuantityError(ValueError):
    """A resource quantity this module can't read."""

    def __init__(self, quantity: str) -> None:
        super().__init__(f"not a quantity: '{quantity}'")


def _quantity(quantity: str, units: dict[str, Decimal]) -> Decimal:
    match = _QUANTITY.match(str(quantity))
    if not match or match.group(2) not in units:
        raise QuantityError(quantity)
    return Decimal(match.group(1)) * units[match.group(2)]


def cpu_millicores(quantity: str) -> int:
    """A Kubernetes CPU quantity in millicores, rounded down."""
    return int(_quantity(quantity, _CPU_UNITS))


def memory_bytes(quantity: str) -> int:
    """A Kubernetes memory quantity in bytes."""
    return int(_quantity(quantity, _MEMORY_UNITS))


def _requests(containers: Iterable[dict]) -> tuple[int, int]:
    cpu = memory = 0
    for c in containers:
        wanted = (c.get("resources") or {}).get("requests") or {}
        cpu += cpu_millicores(wanted.get("cpu", "0"))
        memory += memory_bytes(wanted.get("memory", "0"))
    return cpu, memory


def pod_requests(pod: dict) -> tuple[int, int]:
    """The CPU in millicores and memory in bytes the scheduler reserves for a pod: its
    containers and sidecars together, or its largest init container if that's more."""
    spec = pod.get("spec") or {}
    init = spec.get("initContainers") or []
    sidecars = [c for c in init if c.get("restartPolicy") == "Always"]
    cpu, memory = _requests([*(spec.get("containers") or []), *sidecars])
    for c in init:
        if c.get("restartPolicy") != "Always":
            init_cpu, init_memory = _requests([c])
            cpu, memory = max(cpu, init_cpu), max(memory, init_memory)
    return cpu, memory


def describe_condition(condition: dict) -> str:
    reason = f"{condition['reason']}: " if condition.get("reason") else ""
    return (
        f"{condition.get('type')} is {condition.get('status')}: "
        f"{reason}{condition.get('message', '')}"
    )


def scheduling_problems(pod: dict) -> list[str]:
    """Why the scheduler hasn't placed the pod, if it says so."""
    return [
        describe_condition(c)
        for c in (pod.get("status") or {}).get("conditions") or []
        if c.get("type") == "PodScheduled" and c.get("status") == "False"
    ]


def _holds_resources(pod: dict, node: str) -> bool:
    return (pod.get("spec") or {}).get("nodeName", "") == node and (
        pod.get("status") or {}
    ).get("phase") not in _FINISHED


def _requests_text(pod: dict) -> str:
    cpu, memory = pod_requests(pod)
    return f"{cpu}m CPU, {memory // MI}Mi memory"


def _node_lines(node: dict, pods: list[dict]) -> list[str]:
    name = node["metadata"]["name"]
    allocatable = (node.get("status") or {}).get("allocatable") or {}
    cpu = cpu_millicores(allocatable.get("cpu", "0"))
    memory = memory_bytes(allocatable.get("memory", "0"))
    on_node = sorted(
        (p for p in pods if _holds_resources(p, name)),
        key=lambda p: pod_requests(p)[0],
        reverse=True,
    )
    used_cpu = sum(pod_requests(p)[0] for p in on_node)
    used_memory = sum(pod_requests(p)[1] for p in on_node)
    return [
        f"node {name}: CPU requested {used_cpu}m of {cpu}m allocatable "
        f"({cpu - used_cpu}m free), memory requested {used_memory // MI}Mi of "
        f"{memory // MI}Mi allocatable",
        *(f"  {obj_key(p)}: {_requests_text(p)}" for p in on_node),
    ]


def _unscheduled_line(pod: dict) -> str:
    reason = "; ".join(scheduling_problems(pod)) or "not scheduled yet"
    return (
        f"unscheduled {obj_key(pod)}: requests {_requests_text(pod)}: "
        + reason.removeprefix("PodScheduled is False: ")
    )


def node_allocation(nodes: list[dict], pods: list[dict]) -> list[str]:
    """What the pods on each node request against what it can give, biggest first, and the
    pods no node has been found for, with the scheduler's reason."""
    return [line for node in nodes for line in _node_lines(node, pods)] + [
        _unscheduled_line(p) for p in pods if _holds_resources(p, "")
    ]


def requested_cpu(pods: list[dict]) -> int:
    """The CPU the long-running pods request, scheduled or not, in millicores. A Job's pods
    finish, so they're left to the margin."""
    return sum(
        pod_requests(p)[0]
        for p in pods
        if (p.get("status") or {}).get("phase") not in _FINISHED
        and not any(
            o.get("kind") == "Job" for o in p["metadata"].get("ownerReferences") or []
        )
    )


def _surge(deployment: dict, replicas: int) -> int:
    """How many pods a rollout adds on top of `replicas`: maxSurge, 25% by default, rounded
    up as the Deployment controller does."""
    strategy = (deployment.get("spec") or {}).get("strategy") or {}
    if strategy.get("type") == "Recreate":
        return 0
    max_surge = (strategy.get("rollingUpdate") or {}).get("maxSurge", "25%")
    if isinstance(max_surge, str) and max_surge.endswith("%"):
        return math.ceil(replicas * int(max_surge[:-1]) / 100)
    return int(max_surge)


def planned_cpu(deployments: list[dict], hpas: list[dict]) -> list[tuple[str, int]]:
    """The CPU, in millicores, the Deployments will request on top of what they do now: every
    HorizontalPodAutoscaler scaling its Deployment up to minReplicas, and the largest one
    rollout's surge, as the values change test rolls out one app at a time."""
    minimum = {
        (h["metadata"]["namespace"], h["spec"]["scaleTargetRef"]["name"]): h[
            "spec"
        ].get("minReplicas", 1)
        for h in hpas
        if h["spec"]["scaleTargetRef"].get("kind") == "Deployment"
    }
    planned = []
    surges = []
    for d in deployments:
        meta = d["metadata"]
        replicas = (d.get("spec") or {}).get("replicas", 1)
        target = max(replicas, minimum.get((meta["namespace"], meta["name"]), 0))
        cpu = pod_requests((d.get("spec") or {}).get("template") or {})[0]
        if target > replicas:
            planned.append(
                (
                    f"scale {obj_key(d)} from {replicas} to {target} replicas",
                    (target - replicas) * cpu,
                )
            )
        surge = _surge(d, target)
        surges.append((f"roll out {obj_key(d)} with {surge} more pod", surge * cpu))
    return planned + sorted(surges, key=lambda s: s[1])[-1:]


def room_problems(
    allocatable: int, requested: int, planned: list[tuple[str, int]], margin: int
) -> list[str]:
    """Why the node can't take what is planned on top of what is requested, with `margin` to
    spare, if it can't; all in millicores of CPU."""
    total = requested + sum(cpu for _, cpu in planned) + margin
    if total <= allocatable:
        return []
    return [
        f"the kind node can't take what the tests plan: {requested}m CPU requested + "
        f"{total - requested - margin}m planned + {margin}m margin = {total}m, more than "
        f"the {allocatable}m allocatable",
        *(f"  {what}: {cpu}m" for what, cpu in planned),
    ]
