"""A change to a values ConfigMap reaches its HelmRelease at once.

helm-controller watches the ConfigMaps and Secrets labelled `reconcile.fluxcd.io/watch: Enabled`
and reconciles the HelmReleases whose `valuesFrom` refers to them as soon as they change,
instead of at the HelmRelease's next interval. This check changes the values of one release and
waits for helm-controller to reconcile them, well within that interval, then puts them back.

test_flux_objects.py runs the check after the HelmReleases are ready, before test_prune.
"""

import pykube
import yaml
from checks.conditions import obj_key
from flux_reconcile import wait_until
from pytest_helm_charts.flux.helm_release import HelmReleaseCR

NAMESPACE = "org-org-name"
HELM_RELEASE = "hello-app-dev-1-hello-world"
VALUES_CONFIG_MAP = "hello-app-dev-1-hello-world-values"
# well within the HelmRelease's interval of 5m
WATCH_TIMEOUT_SEC = 90
# the change: an annotation on hello-world's Pods
ANNOTATION = "gitops-template.giantswarm.io/values-watch-test"


def config_digest(hr: HelmReleaseCR) -> str:
    """The digest of the values helm-controller last reconciled the HelmRelease with."""
    hr.reload()
    return (hr.obj.get("status") or {}).get("lastAttemptedConfigDigest", "")


def wait_for_reconcile(hr: HelmReleaseCR, digest: str, what: str) -> None:
    """Wait until helm-controller has reconciled the HelmRelease with other values than
    `digest`."""
    wait_until(
        lambda: (
            [f"HelmRelease '{obj_key(hr.obj)}' has values digest {digest}"]
            if config_digest(hr) == digest
            else []
        ),
        WATCH_TIMEOUT_SEC,
        what,
    )


def with_annotation(values_text: str) -> str:
    """The values in `values_text` with ANNOTATION on the Pods."""
    values = yaml.safe_load(values_text) or {}
    values.setdefault("podAnnotations", {})[ANNOTATION] = "changed"
    return yaml.safe_dump(values)


def check_values_change_applied(api: pykube.HTTPClient) -> None:
    """Change the values ConfigMap of HELM_RELEASE and wait for helm-controller to reconcile
    the release, then put the values back and wait for that, too."""
    hr = HelmReleaseCR.objects(api).filter(namespace=NAMESPACE).get(name=HELM_RELEASE)
    config_map = (
        pykube.ConfigMap.objects(api)
        .filter(namespace=NAMESPACE)
        .get(name=VALUES_CONFIG_MAP)
    )
    original = config_map.obj["data"]["values"]
    digest = config_digest(hr)
    config_map.patch({"data": {"values": with_annotation(original)}})
    try:
        wait_for_reconcile(hr, digest, "the changed values weren't reconciled")
    finally:
        changed = config_digest(hr)
        config_map.patch({"data": {"values": original}})
    wait_for_reconcile(hr, changed, "the restored values weren't reconciled")
