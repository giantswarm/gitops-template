"""N1: reading the notification example from the cluster; commit_status.py judges it."""

from pathlib import Path

import pykube
import pytest
import yaml
from commit_status import (
    alert_problems,
    provider_problems,
    receiver_problems,
    suspended,
)
from flux_reconcile import wait_until
from pykube.objects import NamespacedAPIObject
from pytest_helm_charts.clusters import Cluster

ALERT_FILE = (
    Path(__file__).resolve().parents[2]
    / "management-clusters/MC_NAME/notifications/commit-status-alert.yaml"
)
# not starting with `kubectl`: Flux removes the fields of those managers when it applies
FIELD_MANAGER = "gitops-template-test"
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


@pytest.fixture(scope="module")
def suspended_alert(kube_cluster: Cluster, flux_app_deployment: None) -> None:
    """Create the example's Alert, suspended, before Flux applies the repository.

    Server-side, under a field manager of its own: Flux takes over the fields of the manifest
    and leaves `suspend`. It isn't deleted: the test cluster goes away with it.
    """
    alert = suspended(yaml.safe_load(ALERT_FILE.read_text()))
    kube_cluster.kubectl(
        f"apply --server-side --field-manager={FIELD_MANAGER}",
        std_input=yaml.safe_dump(alert),
    )


def check_notifications(api: pykube.HTTPClient) -> None:
    """Wait until the Provider has its token, the Alert names it, and the Receiver is Ready."""
    wait_until(
        lambda: _problems(api),
        READY_TIMEOUT_SEC,
        "the notification example isn't ready",
    )
