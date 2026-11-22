"""The Flux Operator objects of the ResourceSet examples, and asking Flux Operator to act on them.

A reconcile request sets `reconcile.fluxcd.io/requestedAt`, and Flux Operator copies it to
`status.lastHandledReconcileAt` whatever it did: read the source, skipped it for the schedule,
or waited for a dependency. Waiting for that copy is what makes the checks deterministic.
"""

import time

import pykube
import pytest
from flux_reconcile import wait_until
from pykube.objects import APIObject, NamespacedAPIObject
from resource_set_status import exported_tags, handled, ready_reason

# A provider reads the registry and a ResourceSet applies what it renders in seconds. The
#  management cluster's Kustomization takes longer, as it applies the whole repository.
HANDLED_TIMEOUT_SEC = 120
READY_TIMEOUT_SEC = 180
# the reasons of the Ready condition: the object did its work, or a provider skipped it as
#  its window is closed
SUCCEEDED = "ReconciliationSucceeded"
SKIPPED = "SkippedDueToSchedule"


class ResourceSetInputProviderCR(NamespacedAPIObject):
    version = "fluxcd.controlplane.io/v1"
    endpoint = "resourcesetinputproviders"
    kind = "ResourceSetInputProvider"


class ResourceSetCR(NamespacedAPIObject):
    version = "fluxcd.controlplane.io/v1"
    endpoint = "resourcesets"
    kind = "ResourceSet"


NAMESPACE = "org-org-name"
# the app example: hello-world on two clusters, at a version picked in an upgrade window
APP_PROVIDER = "hello-world-scheduled-version"
APP_RESOURCE_SET = "hello-world-scheduled"
APP_RELEASES = [
    "out-of-band-no-flux-hello-world-scheduled",
    "out-of-band-flux-app-hello-world-scheduled",
]
# the workload of the release in the test's vCluster, (namespace, name)
APP_WORKLOAD = ("hello-world-scheduled", "hello-world-scheduled")
# the cluster example: the scheduled-upgrades cluster, whose ResourceSet renders its
#  OCIRepository and HelmRelease, both named after the cluster, at the release its provider picks
CLUSTER_PROVIDER = "scheduled-upgrades-release"
CLUSTER_RESOURCE_SET = "scheduled-upgrades"
CLUSTER_NAME = "scheduled-upgrades"
# the Kustomizations that apply them, (namespace, name)
APP_KUSTOMIZATION = ("default", "mc-name-multicluster-apps-org-name")
CLUSTER_KUSTOMIZATION = (NAMESPACE, "mc-name-clusters-scheduled-upgrades")
EXAMPLES = [(APP_PROVIDER, APP_RESOURCE_SET), (CLUSTER_PROVIDER, CLUSTER_RESOURCE_SET)]
# their binding in kind-test.yaml
EXAMPLE = "scheduled-upgrades"


def get(api: pykube.HTTPClient, kind: type[APIObject], name: str) -> APIObject:
    return kind.objects(api).filter(namespace=NAMESPACE).get(name=name)


def request(obj: APIObject, patch: dict, force: bool = False) -> None:
    """Apply `patch` with a reconcile request, and wait until Flux Operator has handled it.

    A forced request reads the source even when the window is closed, as
    `flux-operator reconcile inputprovider --force` does.
    """
    token = str(time.time())
    annotations = {"reconcile.fluxcd.io/requestedAt": token}
    if force:
        annotations["reconcile.fluxcd.io/forceAt"] = token
    obj.patch({**patch, "metadata": {"annotations": annotations}})

    def not_handled() -> list[str]:
        obj.reload()
        if handled(obj.obj, token):
            return []
        return [f"{obj.kind} '{obj.name}' hasn't handled the request {token}"]

    wait_until(not_handled, HANDLED_TIMEOUT_SEC, "the request wasn't handled")


def wait_for_reason(obj: APIObject, *reasons: str) -> None:
    """Wait until the reason of the object's Ready condition is one of `reasons`."""

    def other_reason() -> list[str]:
        obj.reload()
        actual = ready_reason(obj.obj)
        if actual in reasons:
            return []
        return [
            f"{obj.kind} '{obj.name}' is {actual or 'without Ready'}, not {reasons}"
        ]

    wait_until(other_reason, READY_TIMEOUT_SEC, f"not {reasons}")


def install_now(api: pykube.HTTPClient, provider: str, resource_set: str) -> None:
    """Force the provider's first reconcile and wait for the ResourceSet to apply its version.

    A new provider whose window is closed exports nothing until the window opens, so a new
    app or cluster isn't installed until then. Its first reconcile, which only adds Flux
    Operator's finalizer, would take a request without acting on it: the request waits for
    the second, which is the one that skips or reads the registry.
    """
    rsip = get(api, ResourceSetInputProviderCR, provider)
    wait_for_reason(rsip, SUCCEEDED, SKIPPED)
    request(rsip, {}, force=True)
    if not provider_tags(api, provider):
        pytest.fail(f"ResourceSetInputProvider '{provider}' exports no version.")
    wait_for_reason(get(api, ResourceSetCR, resource_set), SUCCEEDED)


def provider_tags(api: pykube.HTTPClient, name: str) -> list[str]:
    return exported_tags(get(api, ResourceSetInputProviderCR, name).obj)


def resume(obj: APIObject) -> None:
    """Let Flux reconcile the Kustomization again, as `flux resume` does: it puts back what the
    test changed in the objects it applies."""
    obj.patch({"spec": {"suspend": False}})
    request(obj, {})
