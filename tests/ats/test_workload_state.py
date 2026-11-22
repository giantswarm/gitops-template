"""Checks of the lines workload_state writes about the objects of an app in the workload
cluster; they need no cluster."""

from test_resource_requests import pod
from workload_state import (
    deployment_line,
    event_lines,
    helm_history_lines,
    helm_release_lines,
    hpa_line,
    pod_line,
)


def test_pod_line_says_why_a_pod_isnt_ready() -> None:
    obj = pod("hello-world-abc", "Pending", "kind")
    obj["status"]["containerStatuses"] = [
        {
            "name": "hello-world",
            "ready": False,
            "restartCount": 3,
            "state": {
                "waiting": {"reason": "ImagePullBackOff", "message": "rate limited"}
            },
        }
    ]
    assert pod_line(obj) == (
        "hello-world/hello-world-abc Pending node=kind ready=0/1 restarts=3; "
        "hello-world waiting: ImagePullBackOff: rate limited"
    )


def test_pod_line_says_why_a_pod_isnt_scheduled() -> None:
    obj = pod(
        "hello-world-abc",
        "Pending",
        conditions=[
            {
                "type": "PodScheduled",
                "status": "False",
                "reason": "Unschedulable",
                "message": "0/1 nodes are available",
            }
        ],
    )
    assert pod_line(obj) == (
        "hello-world/hello-world-abc Pending node=- ready=0/0 restarts=0; "
        "PodScheduled is False: Unschedulable: 0/1 nodes are available"
    )


def test_deployment_line_has_the_replicas_and_conditions() -> None:
    obj = {
        "metadata": {"name": "hello-world", "namespace": "hello-world"},
        "spec": {"replicas": 4},
        "status": {
            "replicas": 4,
            "updatedReplicas": 4,
            "readyReplicas": 1,
            "availableReplicas": 1,
            "unavailableReplicas": 3,
            "conditions": [
                {
                    "type": "Available",
                    "status": "False",
                    "reason": "MinimumReplicasUnavailable",
                    "message": "Deployment does not have minimum availability.",
                }
            ],
        },
    }
    assert deployment_line(obj) == (
        "hello-world/hello-world replicas=4 updated=4 ready=1 available=1 unavailable=3; "
        "Available is False: MinimumReplicasUnavailable: "
        "Deployment does not have minimum availability."
    )


def test_hpa_line_has_the_scale_and_conditions() -> None:
    obj = {
        "metadata": {"name": "hello-world", "namespace": "hello-world"},
        "spec": {"minReplicas": 4, "maxReplicas": 100},
        "status": {
            "currentReplicas": 1,
            "desiredReplicas": 4,
            "conditions": [
                {
                    "type": "ScalingLimited",
                    "status": "True",
                    "reason": "TooFewReplicas",
                    "message": "the desired replica count is less than the minimum",
                }
            ],
        },
    }
    assert hpa_line(obj) == (
        "hello-world/hello-world min=4 max=100 current=1 desired=4; "
        "ScalingLimited is True: TooFewReplicas: "
        "the desired replica count is less than the minimum"
    )


def test_helm_history_comes_from_the_storage_secrets() -> None:
    def release(version: str, status: str) -> dict:
        return {
            "metadata": {
                "name": f"sh.helm.release.v1.hello-world.v{version}",
                "namespace": "hello-world",
                "labels": {
                    "owner": "helm",
                    "name": "hello-world",
                    "version": version,
                    "status": status,
                    "modifiedAt": "1795000000",
                },
            }
        }

    secrets = [
        release("10", "pending-upgrade"),
        release("2", "superseded"),
        {"metadata": {"name": "other", "namespace": "hello-world", "labels": {}}},
    ]
    assert helm_history_lines(secrets) == [
        "hello-world/hello-world v2 superseded modifiedAt=1795000000",
        "hello-world/hello-world v10 pending-upgrade modifiedAt=1795000000",
    ]


def test_helm_release_lines_have_the_conditions_and_history() -> None:
    obj = {
        "metadata": {"name": "hello", "namespace": "org-org-name"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "False",
                    "reason": "UpgradeFailed",
                    "message": "context deadline exceeded",
                }
            ],
            "lastAttemptedConfigDigest": "sha256:b",
            "upgradeFailures": 1,
            "history": [
                {
                    "version": 2,
                    "status": "failed",
                    "chartVersion": "3.2.2",
                    "configDigest": "sha256:b",
                    "lastDeployed": "2026-11-21T23:40:00Z",
                }
            ],
        },
    }
    assert helm_release_lines(obj) == [
        "HelmRelease org-org-name/hello: lastAttemptedConfigDigest=sha256:b "
        "installFailures=0 upgradeFailures=1",
        "  Ready is False: UpgradeFailed: context deadline exceeded",
        "  history: v2 failed chart=3.2.2 config=sha256:b lastDeployed=2026-11-21T23:40:00Z",
    ]


def test_event_lines_are_the_latest_in_time_order() -> None:
    def event(name: str, time: str) -> dict:
        return {
            "metadata": {"name": name, "namespace": "hello-world"},
            "lastTimestamp": time,
            "type": "Warning",
            "reason": "FailedScheduling",
            "involvedObject": {"kind": "Pod", "name": name},
            "message": "Insufficient cpu",
            "count": 2,
        }

    events = [event("b", "2026-11-21T10:02:00Z"), event("a", "2026-11-21T10:01:00Z")]
    assert event_lines(events, limit=1) == [
        "2026-11-21T10:02:00Z Warning FailedScheduling hello-world Pod/b: "
        "Insufficient cpu (x2)"
    ]


def test_event_lines_fall_back_to_the_event_time() -> None:
    obj = {
        "metadata": {"name": "e", "namespace": "ns"},
        "eventTime": "2026-11-21T10:00:00.000000Z",
        "type": "Normal",
        "reason": "Scheduled",
        "involvedObject": {"kind": "Pod", "name": "p"},
        "message": "assigned",
    }
    assert event_lines([obj], limit=5) == [
        "2026-11-21T10:00:00.000000Z Normal Scheduled ns Pod/p: assigned (x1)"
    ]
