"""N1: the notification example, commit statuses on GitHub and a Receiver for push events.

The example's Provider posts a commit status to GitHub for every event of the Kustomizations.
The kind test must not call GitHub, so it creates the Alert, suspended, before Flux applies the
repository: notification-controller then sends nothing. Flux applies the Alert over it and
leaves `suspend` alone, as the test's own field manager owns it. The check, in
notification_objects.py, proves the rest: Flux applied the objects, External Secrets Operator
wrote the tokens from the test's fake store, the Alert names the Provider, and the Receiver is
Ready. This module judges what it reads.
"""

import copy

from checks.conditions import is_ready, not_ready_reason, obj_key


def suspended(alert: dict) -> dict:
    """A copy of the Alert manifest `alert` with `spec.suspend` set."""
    patched = copy.deepcopy(alert)
    patched["spec"]["suspend"] = True
    return patched


def provider_problems(provider: dict | None, secret: dict | None) -> list[str]:
    """Why the Provider can't authenticate, if it can't: its Secret has to hold a `token`."""
    if provider is None:
        return ["the Provider isn't there"]
    secret_name = provider["spec"]["secretRef"]["name"]
    prefix = f"Provider '{obj_key(provider)}': Secret '{secret_name}'"
    if secret is None:
        return [f"{prefix} isn't there"]
    if "token" not in (secret.get("data") or {}):
        return [f"{prefix} has no 'token'"]
    return []


def alert_problems(alert: dict | None, provider: dict | None) -> list[str]:
    """Why the Alert doesn't resolve to the Provider, or would call GitHub, if so."""
    if alert is None:
        return ["the Alert isn't there"]
    provider_name = alert["spec"]["providerRef"]["name"]
    if provider is None or provider["metadata"]["name"] != provider_name:
        return [f"Alert '{obj_key(alert)}': Provider '{provider_name}' isn't there"]
    if not alert["spec"].get("suspend"):
        return [
            f"Alert '{obj_key(alert)}' isn't suspended: the test would post commit"
            " statuses to GitHub"
        ]
    return []


def receiver_problems(receiver: dict | None) -> list[str]:
    """Why the Receiver isn't Ready, if it isn't."""
    if receiver is None:
        return ["the Receiver isn't there"]
    if is_ready(receiver):
        return []
    return [f"Receiver '{obj_key(receiver)}': {not_ready_reason(receiver)}"]
