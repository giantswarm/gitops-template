"""What the pods on a node request against what the node can give, and why the scheduler hasn't
placed a pod. The kind cluster is one node on a CI runner, so the CPU the test's workloads request
decides whether a pod runs or stays Pending; workload_diagnostics reports it (#368)."""

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
