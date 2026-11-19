"""N1: suspending the notification example's Alert and waiting for its Receiver; commit_status.py
judges the Receiver, assertions/exists/notifications the rest."""

from pathlib import Path

import pykube
import pytest
import yaml
from checks.kinds import ReceiverCR
from commit_status import receiver_problems, suspended
from flux_reconcile import wait_until
from pytest_helm_charts.clusters import Cluster

ALERT_FILE = (
    Path(__file__).resolve().parents[2]
    / "management-clusters/MC_NAME/notifications/commit-status-alert.yaml"
)
# not starting with `kubectl`: Flux removes the fields of those managers when it applies
FIELD_MANAGER = "gitops-template-test"
NAMESPACE = "default"
RECEIVER = "github-push"
# ESO writes the webhook secret within seconds of the store being Ready; the Receiver follows
READY_TIMEOUT_SEC = 120


def _problems(api: pykube.HTTPClient) -> list[str]:
    receiver = (
        ReceiverCR.objects(api).filter(namespace=NAMESPACE).get_or_none(name=RECEIVER)
    )
    return receiver_problems(receiver.obj if receiver is not None else None)


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
    """Wait until the Receiver is Ready."""
    wait_until(
        lambda: _problems(api),
        READY_TIMEOUT_SEC,
        "the notification example's Receiver isn't Ready",
    )
