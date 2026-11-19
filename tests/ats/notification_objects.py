"""N1: reading the notification example from the cluster; commit_status.py judges it."""

import pykube
from commit_status import alert_problems, provider_problems, receiver_problems
from flux_reconcile import wait_until
from pykube.objects import NamespacedAPIObject

NAMESPACE = "default"
PROVIDER = "github-commit-status"
ALERT = "github-commit-status"
RECEIVER = "github-push"
# ESO writes the tokens within seconds of the store being Ready; the Receiver follows
READY_TIMEOUT_SEC = 120


class ProviderCR(NamespacedAPIObject):
    version = "notification.toolkit.fluxcd.io/v1beta3"
    endpoint = "providers"
    kind = "Provider"


class AlertCR(NamespacedAPIObject):
    version = "notification.toolkit.fluxcd.io/v1beta3"
    endpoint = "alerts"
    kind = "Alert"


class ReceiverCR(NamespacedAPIObject):
    version = "notification.toolkit.fluxcd.io/v1"
    endpoint = "receivers"
    kind = "Receiver"


def _get(
    api: pykube.HTTPClient, cls: type[NamespacedAPIObject], name: str
) -> dict | None:
    obj = cls.objects(api).filter(namespace=NAMESPACE).get_or_none(name=name)
    return obj.obj if obj is not None else None


def _problems(api: pykube.HTTPClient) -> list[str]:
    provider = _get(api, ProviderCR, PROVIDER)
    secret = None
    if provider is not None:
        secret = _get(api, pykube.Secret, provider["spec"]["secretRef"]["name"])
    return (
        provider_problems(provider, secret)
        + alert_problems(_get(api, AlertCR, ALERT), provider)
        + receiver_problems(_get(api, ReceiverCR, RECEIVER))
    )


def check_notifications(api: pykube.HTTPClient) -> None:
    """Wait until the Provider has its token, the Alert names it, and the Receiver is Ready."""
    # TEMPORARY DEBUG
    import logging

    from pytest_helm_charts.flux.kustomization import KustomizationCR

    log = logging.getLogger(__name__)
    root = (
        KustomizationCR.objects(api)
        .filter(namespace=NAMESPACE)
        .get(name="mc-name-gitops")
    )
    log.error(f"DEBUG root spec: {root.obj['spec']}")
    log.error(f"DEBUG root status: {root.obj.get('status')}")
    alert = AlertCR.objects(api).filter(namespace=NAMESPACE).get(name=ALERT)
    log.error(f"DEBUG alert: {alert.obj}")
    wait_until(
        lambda: _problems(api),
        READY_TIMEOUT_SEC,
        "the notification example isn't ready",
    )
