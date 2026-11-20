"""N1: suspending the notification example's Alerts and waiting for its token Secrets and its
Receiver; commit_status.py judges them, assertions/exists/notifications the rest."""

from pathlib import Path

import pykube
import pytest
import yaml
from checks.kinds import ReceiverCR
from commit_status import (
    receiver_problems,
    suspended,
    suspended_alerts,
    token_problems,
)
from conftest import run_tool
from fake_store import FAKE_STORE_DATA
from flux_reconcile import wait_until
from pytest_helm_charts.clusters import Cluster

MC_DIR = Path(__file__).resolve().parents[2] / "management-clusters/MC_NAME"
# the management cluster's Alert, for the Kustomizations in `default`
ALERT_FILE = MC_DIR / "notifications/commit-status-alert.yaml"
# the organisation's directory, whose build holds its own Alert, in the organisation's
#  namespace: its kustomization.yaml completes the namespace, so it's built, not read
ORG_DIR = MC_DIR / "organizations/ORG_NAME"
KUBECTL_URL = "https://kubernetes.io/docs/tasks/tools/"
# not starting with `kubectl`: Flux removes the fields of those managers when it applies
FIELD_MANAGER = "gitops-template-test"
NAMESPACE = "default"
ORG_NAMESPACE = "org-org-name"
RECEIVER = "github-push"
# (namespace, name) of the Secrets ESO writes from the fake store's keys of the same name under
#  gitops/: each Provider's token, and the Receiver's
TOKEN_SECRETS = (
    (NAMESPACE, "github-commit-status-token"),
    (ORG_NAMESPACE, "github-commit-status-token"),
    (NAMESPACE, "github-webhook-token"),
)
# ESO writes the webhook secret within seconds of the store being Ready; the Receiver follows
READY_TIMEOUT_SEC = 120


def _token_problems(api: pykube.HTTPClient) -> list[str]:
    store = {item["key"]: item["value"] for item in FAKE_STORE_DATA}
    return [
        problem
        for namespace, name in TOKEN_SECRETS
        for problem in token_problems(
            f"{namespace}/{name}",
            getattr(
                pykube.Secret.objects(api)
                .filter(namespace=namespace)
                .get_or_none(name=name),
                "obj",
                None,
            ),
            store[f"gitops/{name}"],
        )
    ]


def _problems(api: pykube.HTTPClient) -> list[str]:
    receiver = (
        ReceiverCR.objects(api).filter(namespace=NAMESPACE).get_or_none(name=RECEIVER)
    )
    return _token_problems(api) + receiver_problems(
        receiver.obj if receiver is not None else None
    )


@pytest.fixture(scope="module")
def suspended_alert(
    kube_cluster: Cluster, flux_app_deployment: None, init_namespaces: None
) -> None:
    """Create the example's Alerts, suspended, before Flux applies the repository: the
    management cluster's, and the organisation's as its directory builds it, in the
    organisation's namespace, which init_namespaces creates.

    Server-side, under a field manager of its own: Flux takes over the fields of the manifests
    and leaves `suspend`. They aren't deleted: the test cluster goes away with them.
    """
    org_build = run_tool("kubectl", KUBECTL_URL, "kustomize", str(ORG_DIR))
    alerts = [
        suspended(yaml.safe_load(ALERT_FILE.read_text())),
        *suspended_alerts(list(yaml.safe_load_all(org_build))),
    ]
    if len(alerts) != 2:
        pytest.fail(f"The organisation's build in {ORG_DIR} has no single Alert.")
    kube_cluster.kubectl(
        f"apply --server-side --field-manager={FIELD_MANAGER}",
        std_input=yaml.safe_dump_all(alerts),
    )


def check_notifications(api: pykube.HTTPClient) -> None:
    """Wait until ESO has written the tokens and the Receiver is Ready."""
    wait_until(
        lambda: _problems(api),
        READY_TIMEOUT_SEC,
        "the notification example's tokens or Receiver aren't ready",
    )
