"""A change to a values ConfigMap reaches its HelmRelease at once.

helm-controller watches the ConfigMaps and Secrets labelled `reconcile.fluxcd.io/watch: Enabled`
and reconciles the HelmReleases whose `valuesFrom` refers to them as soon as they change,
instead of at the HelmRelease's next interval. This check changes the values of one release and
waits for helm-controller to reconcile them, well within that interval, then puts them back.

test_flux_objects.py runs the check after the HelmReleases are ready, before test_prune.
"""

import pykube
import yaml
from checks.conditions import is_ready, obj_key
from flux_reconcile import suspend, wait_until
from pytest_helm_charts.flux.helm_release import HelmReleaseCR
from pytest_helm_charts.flux.kustomization import KustomizationCR

NAMESPACE = "org-org-name"
HELM_RELEASE = "hello-app-dev-1-hello-world"
VALUES_CONFIG_MAP = "hello-app-dev-1-hello-world-values"
# a tenth of the HelmRelease's interval of 5m, so a scheduled reconcile rarely lands in it
WATCH_TIMEOUT_SEC = 30
# the upgrade with the changed values, once helm-controller has picked them up
UPGRADE_TIMEOUT_SEC = 300
# the change: an annotation on hello-world's Pods
ANNOTATION = "gitops-template.giantswarm.io/values-watch-test"


def config_digest(hr: HelmReleaseCR) -> str:
    """The digest of the values helm-controller last reconciled the HelmRelease with."""
    hr.reload()
    return (hr.obj.get("status") or {}).get("lastAttemptedConfigDigest", "")


def wait_for_reconcile(hr: HelmReleaseCR, digest: str, what: str) -> None:
    """Wait until helm-controller has started reconciling the HelmRelease with other values
    than `digest`, then until the release is Ready with them."""
    wait_until(
        lambda: (
            [f"HelmRelease '{obj_key(hr.obj)}' has values digest {digest}"]
            if config_digest(hr) == digest
            else []
        ),
        WATCH_TIMEOUT_SEC,
        what,
    )
    wait_until(
        lambda: (
            [] if is_ready(hr.obj) else [f"HelmRelease '{obj_key(hr.obj)}' isn't Ready"]
        ),
        UPGRADE_TIMEOUT_SEC,
        f"{what}: the upgrade didn't finish",
    )


def owning_kustomization(api: pykube.HTTPClient, obj: dict) -> KustomizationCR:
    """The Flux Kustomization that applied `obj`, from the labels Flux sets on it."""
    labels = obj["metadata"]["labels"]
    return (
        KustomizationCR.objects(api)
        .filter(namespace=labels["kustomize.toolkit.fluxcd.io/namespace"])
        .get(name=labels["kustomize.toolkit.fluxcd.io/name"])
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
    # kustomize-controller would put the ConfigMap back at its next apply
    kustomization = owning_kustomization(api, config_map.obj)
    suspend(kustomization)
    try:
        config_map.patch({"data": {"values": with_annotation(original)}})
        try:
            wait_for_reconcile(hr, digest, "the changed values weren't reconciled")
        finally:
            changed = config_digest(hr)
            config_map.patch({"data": {"values": original}})
        wait_for_reconcile(hr, changed, "the restored values weren't reconciled")
    finally:
        kustomization.patch({"spec": {"suspend": False}})
