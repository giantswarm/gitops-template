"""Waits for an ESO object to get Ready, with ESO's log about it when it doesn't.

The provider's error, such as a store that can't reach its API server, is only in ESO's log, so a
failed wait adds the log's last lines that name the object. The log is read once, when the wait
fails, not on every poll.
"""

from collections.abc import Callable

import pykube
import pytest
import requests
from checks.conditions import condition_true, obj_key
from external_secrets import ESO_NAMESPACE, ESO_RELEASE_NAME
from flux_reconcile import wait_until
from pykube.exceptions import PyKubeError
from pykube.objects import NamespacedAPIObject

# how far back in ESO's log a failure looks for the reason
ESO_LOG_LINES = 200


def ready_problems(
    api: pykube.HTTPClient, kind: type[NamespacedAPIObject], namespace: str, name: str
) -> list[str]:
    """Why the ESO object `namespace/name` isn't Ready, if it isn't."""
    obj = kind.objects(api).filter(namespace=namespace).get_or_none(name=name)
    if obj is None:
        return [f"{kind.kind} '{namespace}/{name}' doesn't exist"]
    if not condition_true(obj.obj, "Ready"):
        return [
            f"{kind.kind} '{obj_key(obj.obj)}' isn't Ready: {obj.obj.get('status')}"
        ]
    return []


def log_lines_about(log: str, namespace: str, name: str) -> list[str]:
    """The last three lines of an ESO log about the object `name` in `namespace`.

    controller-runtime adds the object's `name` and `namespace` to every line it logs while it
    reconciles one; a plain search for a name such as `default` would match other lines too.
    """
    keys = (f'"name":"{name}"', f'"namespace":"{namespace}"')
    return [f"  {line}" for line in log.splitlines() if all(k in line for k in keys)][
        -3:
    ]


def wait_ready(
    api: pykube.HTTPClient,
    kind: type[NamespacedAPIObject],
    namespace: str,
    name: str,
    what: str,
    timeout_sec: int,
    more: Callable[[], list[str]] = list,
) -> None:
    """Wait for `namespace/name` to be Ready and `more` to find nothing."""
    try:
        wait_until(
            lambda: ready_problems(api, kind, namespace, name) + more(),
            timeout_sec,
            what,
        )
    except pytest.fail.Exception as failure:
        pytest.fail(
            "\n".join(
                [str(failure), "ESO's log about it:", *eso_log(api, namespace, name)]
            )
        )


def eso_log(api: pykube.HTTPClient, namespace: str, name: str) -> list[str]:
    """ESO's log lines about `namespace/name`, or why they couldn't be read."""
    try:
        pods = pykube.Pod.objects(api).filter(
            namespace=ESO_NAMESPACE,
            selector={"app.kubernetes.io/name": ESO_RELEASE_NAME},
        )
        return [
            line
            for pod in pods
            for line in log_lines_about(
                pod.logs(tail_lines=ESO_LOG_LINES), namespace, name
            )
        ]
    except (requests.RequestException, PyKubeError) as error:
        return [f"  couldn't read it: {error}"]
