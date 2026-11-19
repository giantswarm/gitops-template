"""Temporary: log the kind cluster's state when the HelmReleases don't get ready."""

import logging

import pykube

logger = logging.getLogger(__name__)


def pod_line(pod: dict) -> str:
    spec, status = pod.get("spec", {}), pod.get("status", {})
    cpu = [
        c.get("resources", {}).get("requests", {}).get("cpu", "-")
        for c in spec.get("containers", [])
    ]
    waiting = [
        c["state"]["waiting"].get("reason", "")
        for c in status.get("containerStatuses", [])
        if "waiting" in c.get("state", {})
    ]
    unscheduled = [
        c.get("message", "")
        for c in status.get("conditions", [])
        if c.get("type") == "PodScheduled" and c.get("status") != "True"
    ]
    meta = pod["metadata"]
    return (
        f"{meta['namespace']}/{meta['name']} {status.get('phase')} node={spec.get('nodeName')} "
        f"cpu={cpu} waiting={waiting} unscheduled={unscheduled}"
    )


def log_state(api: pykube.HTTPClient) -> None:
    for node in pykube.Node.objects(api):
        logger.error(
            f"DEBUG node {node.name} allocatable={node.obj['status'].get('allocatable')}"
        )
    pods = [p.obj for p in pykube.Pod.objects(api).filter(namespace=pykube.all)]
    for pod in pods:
        logger.error(f"DEBUG pod {pod_line(pod)}")
    events = [e.obj for e in pykube.Event.objects(api).filter(namespace=pykube.all)]
    events.sort(key=lambda e: e.get("lastTimestamp") or e.get("eventTime") or "")
    for e in events[-100:]:
        involved = e["involvedObject"]
        logger.error(
            f"DEBUG event {involved.get('namespace')}/{involved.get('name')}: "
            f"{e.get('reason')} {e.get('message')}"
        )


def log_cluster_state(api: pykube.HTTPClient) -> None:
    """Log node allocatable, every pod with its CPU requests and state, and the last 100 events."""
    try:
        log_state(api)
    except Exception:  # debugging only, never fail the check here
        logger.exception("DEBUG couldn't log the cluster state")
