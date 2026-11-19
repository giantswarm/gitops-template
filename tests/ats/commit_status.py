"""N1: the notification example, commit statuses on GitHub and a Receiver for push events.

The example's Provider posts a commit status to GitHub for every event of the Kustomizations.
The kind test must not call GitHub, so it creates the Alert, suspended, before Flux applies the
repository: notification-controller then sends nothing. Flux applies the Alert over it and
leaves `suspend` alone, as the test's own field manager owns it. The assertions in
assertions/exists/notifications prove the rest: Flux applied the objects, External Secrets
Operator wrote the tokens from the test's fake store, and the Alert names the Provider and
stays suspended. notification_objects.py waits for the Receiver to be Ready, which this module
judges.
"""

import copy

from checks.conditions import is_ready, not_ready_reason, obj_key


def suspended(alert: dict) -> dict:
    """A copy of the Alert manifest `alert` with `spec.suspend` set."""
    patched = copy.deepcopy(alert)
    patched["spec"]["suspend"] = True
    return patched


def receiver_problems(receiver: dict | None) -> list[str]:
    """Why the Receiver isn't Ready, if it isn't."""
    if receiver is None:
        return ["the Receiver isn't there"]
    if is_ready(receiver):
        return []
    return [f"Receiver '{obj_key(receiver)}': {not_ready_reason(receiver)}"]
