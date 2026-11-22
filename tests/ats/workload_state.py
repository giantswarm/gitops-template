"""One line for each object that says whether an app in the workload cluster runs, and if not,
why: its HelmRelease and Helm history, its Deployment, ReplicaSets, HorizontalPodAutoscaler,
PodDisruptionBudget and Pods, and the events. workload_diagnostics reports them (#368).
"""

from collections.abc import Iterable

from checks.conditions import obj_key
from resource_requests import describe_condition, scheduling_problems


def _conditions(obj: dict) -> list[str]:
    conditions = (obj.get("status") or {}).get("conditions") or []
    return [describe_condition(c) for c in conditions]


def _container_problems(status: dict) -> list[str]:
    return [
        f"{c.get('name')} {state}: {detail.get('reason', '')}: "
        f"{detail.get('message', '')}".rstrip(": ")
        for c in status.get("containerStatuses") or []
        for state, detail in (c.get("state") or {}).items()
        if state in ("waiting", "terminated") and detail
    ]


def pod_line(pod: dict) -> str:
    """A pod's phase, node, readiness and restarts, and why it isn't running or ready."""
    status = pod.get("status") or {}
    containers = status.get("containerStatuses") or []
    ready = sum(1 for c in containers if c.get("ready"))
    restarts = sum(c.get("restartCount", 0) for c in containers)
    node = (pod.get("spec") or {}).get("nodeName") or "-"
    return "; ".join(
        [
            f"{obj_key(pod)} {status.get('phase')} node={node} "
            f"ready={ready}/{len(containers)} restarts={restarts}",
            *scheduling_problems(pod),
            *_container_problems(status),
        ]
    )


def _replicas_line(obj: dict, fields: Iterable[tuple[str, str]]) -> str:
    status = obj.get("status") or {}
    spec = obj.get("spec") or {}
    counts = " ".join(f"{label}={status.get(field, 0)}" for label, field in fields)
    return "; ".join(
        [
            f"{obj_key(obj)} replicas={spec.get('replicas', '-')} {counts}",
            *_conditions(obj),
        ]
    )


def deployment_line(deployment: dict) -> str:
    return _replicas_line(
        deployment,
        [
            ("updated", "updatedReplicas"),
            ("ready", "readyReplicas"),
            ("available", "availableReplicas"),
            ("unavailable", "unavailableReplicas"),
        ],
    )


def replica_set_line(replica_set: dict) -> str:
    return _replicas_line(
        replica_set, [("ready", "readyReplicas"), ("available", "availableReplicas")]
    )


def hpa_line(hpa: dict) -> str:
    spec = hpa.get("spec") or {}
    status = hpa.get("status") or {}
    return "; ".join(
        [
            f"{obj_key(hpa)} min={spec.get('minReplicas')} max={spec.get('maxReplicas')} "
            f"current={status.get('currentReplicas')} "
            f"desired={status.get('desiredReplicas')}",
            *_conditions(hpa),
        ]
    )


def pdb_line(pdb: dict) -> str:
    spec = pdb.get("spec") or {}
    status = pdb.get("status") or {}
    budget = " ".join(
        f"{k}={spec[k]}" for k in ("minAvailable", "maxUnavailable") if k in spec
    )
    return (
        f"{obj_key(pdb)} {budget} healthy={status.get('currentHealthy')}/"
        f"{status.get('expectedPods')} "
        f"disruptionsAllowed={status.get('disruptionsAllowed')}"
    )


def helm_history_lines(secrets: list[dict]) -> list[str]:
    """`helm history` of every release, from the Secrets Helm stores its releases in."""
    releases = sorted(
        (
            s["metadata"]
            for s in secrets
            if (s["metadata"].get("labels") or {}).get("owner") == "helm"
        ),
        key=lambda m: (
            m["namespace"],
            m["labels"]["name"],
            int(m["labels"]["version"]),
        ),
    )
    return [
        f"{m['namespace']}/{m['labels']['name']} v{m['labels']['version']} "
        f"{m['labels'].get('status')} modifiedAt={m['labels'].get('modifiedAt')}"
        for m in releases
    ]


def helm_release_lines(hr: dict) -> list[str]:
    """A HelmRelease's conditions, what helm-controller last attempted, and its history."""
    status = hr.get("status") or {}
    return [
        f"HelmRelease {obj_key(hr)}: "
        f"lastAttemptedConfigDigest={status.get('lastAttemptedConfigDigest')} "
        f"installFailures={status.get('installFailures', 0)} "
        f"upgradeFailures={status.get('upgradeFailures', 0)}",
        *(f"  {c}" for c in _conditions(hr)),
        *(
            f"  history: v{h.get('version')} {h.get('status')} "
            f"chart={h.get('chartVersion')} config={h.get('configDigest')} "
            f"lastDeployed={h.get('lastDeployed')}"
            for h in status.get("history") or []
        ),
    ]


def _event_time(event: dict) -> str:
    return (
        event.get("lastTimestamp")
        or event.get("eventTime")
        or event["metadata"].get("creationTimestamp")
        or ""
    )


def event_lines(events: list[dict], limit: int) -> list[str]:
    """The newest `limit` events, oldest first."""
    newest = sorted(events, key=_event_time)[-limit:]
    return [
        f"{_event_time(e)} {e.get('type')} {e.get('reason')} {e['metadata']['namespace']} "
        f"{e['involvedObject'].get('kind')}/{e['involvedObject'].get('name')}: "
        f"{e.get('message', '').strip()} (x{e.get('count') or 1})"
        for e in newest
    ]
