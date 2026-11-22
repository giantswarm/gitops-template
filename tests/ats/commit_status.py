"""N1: the notification example, commit statuses on GitHub and a Receiver for push events.

The example's Providers post a commit status to GitHub for every event of the Kustomizations:
the management cluster's for those in `default`, the organisation's for those in its namespace.
The kind test must not call GitHub, so it creates both Alerts, suspended, before Flux applies
the repository: notification-controller then sends nothing. Flux applies the Alerts over them
and leaves `suspend` alone, as the test's own field manager owns it. The assertions in
assertions/exists/notifications prove that Flux applied the objects and that each Alert names
its Provider and stays suspended. notification_objects.py waits until External Secrets Operator
has written each token Secret's `token` from the test's fake store and the Receiver is Ready,
both of which this module judges. It also judges which event messages an Alert drops, which
test_commit_status.py checks against the example's Alerts.
"""

import base64
import copy
import re

from checks.conditions import is_ready, not_ready_reason, obj_key


def suspended(alert: dict) -> dict:
    """A copy of the Alert manifest `alert` with `spec.suspend` set."""
    patched = copy.deepcopy(alert)
    patched["spec"]["suspend"] = True
    return patched


def suspended_alerts(manifests: list[dict | None]) -> list[dict]:
    """A suspended copy of every Alert among `manifests`, such as the documents of a build."""
    return [suspended(m) for m in manifests if m and m.get("kind") == "Alert"]


def excluded(alert: dict, message: str) -> bool:
    """Whether the Alert `alert` drops an event with `message`: as notification-controller does,
    whether any pattern of its `exclusionList` matches anywhere in the message. Go's and
    Python's regular expressions agree on the patterns the example uses."""
    patterns = alert["spec"].get("exclusionList") or []
    return any(re.search(pattern, message) for pattern in patterns)


def receiver_problems(receiver: dict | None) -> list[str]:
    """Why the Receiver isn't Ready, if it isn't."""
    if receiver is None:
        return ["the Receiver isn't there"]
    if is_ready(receiver):
        return []
    return [f"Receiver '{obj_key(receiver)}': {not_ready_reason(receiver)}"]


def token_problems(name: str, secret: dict | None, expected: str) -> list[str]:
    """Why the token Secret `name`, as `secret`, doesn't hold `expected` as its `token`, if it
    doesn't."""
    if secret is None:
        return [f"Secret '{name}' isn't there"]
    encoded = (secret.get("data") or {}).get("token")
    if not encoded:
        return [f"Secret '{name}' has no 'token'"]
    if base64.b64decode(encoded).decode() != expected:
        return [f"Secret '{name}' has another 'token' than the store's"]
    return []
