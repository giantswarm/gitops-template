"""T2: an organization's Kustomization can't create objects in another organization's
namespace.

An organization's Kustomizations run as its `automation` ServiceAccount, which is admin of
the organization's namespace only, see automation_rbac. The check creates a second
organization namespace and, in the example organization's namespace, a Kustomization that
puts a ConfigMap into it with `targetNamespace`. Kubernetes has to refuse the ConfigMap.
test_flux_objects.py runs it once the Kustomizations are ready.
"""

import pykube
import pytest
from checks.conditions import obj_key
from cluster_gates import ready_condition
from conftest import (
    FLUX_GIT_REPO_NAME,
    FLUX_IMPERSONATION_SA_NAME,
    FLUX_OBJECTS_NAMESPACE,
)
from flux_reconcile import wait_until
from pytest_helm_charts.flux.kustomization import KustomizationCR

ORGANIZATION_NAMESPACE = "org-org-name"
# the other organization: the Kustomization tries to create its ConfigMap here
OTHER_ORGANIZATION_NAMESPACE = "org-tenancy-test"
KUSTOMIZATION_NAME = "tenancy-test"
# a directory with a single namespaced object, the ConfigMap `CONFIG_MAP`
PATH = (
    "./management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/"
    "WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band"
)
CONFIG_MAP = "secret-to-be-created-directly-in-wc"
# who Kubernetes refuses: the organization's ServiceAccount
REFUSED_USER = (
    f"system:serviceaccount:{ORGANIZATION_NAMESPACE}:{FLUX_IMPERSONATION_SA_NAME}"
)
REFUSAL_TIMEOUT_SEC = 120


def tenancy_kustomization(api: pykube.HTTPClient) -> KustomizationCR:
    """The Kustomization of the example organization that targets the other one's namespace."""
    return KustomizationCR(
        api,
        {
            "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
            "kind": "Kustomization",
            "metadata": {
                "name": KUSTOMIZATION_NAME,
                "namespace": ORGANIZATION_NAMESPACE,
            },
            "spec": {
                "interval": "10m",
                "path": PATH,
                "prune": False,
                "serviceAccountName": FLUX_IMPERSONATION_SA_NAME,
                "sourceRef": {
                    "kind": "GitRepository",
                    "name": FLUX_GIT_REPO_NAME,
                    "namespace": FLUX_OBJECTS_NAMESPACE,
                },
                "targetNamespace": OTHER_ORGANIZATION_NAMESPACE,
            },
        },
    )


def refusal_problems(kustomization: KustomizationCR) -> list[str]:
    """Why the Kustomization doesn't report that Kubernetes refused its ServiceAccount, if it
    doesn't."""
    kustomization.reload()
    ready = ready_condition(kustomization.obj)
    message = ready.get("message", "")
    if (
        ready.get("status") == "False"
        and "forbidden" in message
        and REFUSED_USER in message
    ):
        return []
    return [
        f"Kustomization '{obj_key(kustomization.obj)}' isn't refused as {REFUSED_USER}: "
        f"Ready is {ready.get('status')}: {message}"
    ]


def check_other_organization_refused(api: pykube.HTTPClient) -> None:
    """Create the other organization's namespace and the Kustomization, wait until Kubernetes
    refuses it, and check that the ConfigMap isn't in the other organization's namespace.
    """
    namespace = pykube.Namespace(
        api, {"metadata": {"name": OTHER_ORGANIZATION_NAMESPACE}}
    )
    namespace.create()
    kustomization = tenancy_kustomization(api)
    try:
        kustomization.create()
        wait_until(
            lambda: refusal_problems(kustomization),
            REFUSAL_TIMEOUT_SEC,
            "Kubernetes didn't keep the Kustomization out of the other namespace",
        )
        copy = (
            pykube.ConfigMap.objects(api)
            .filter(namespace=OTHER_ORGANIZATION_NAMESPACE)
            .get_or_none(name=CONFIG_MAP)
        )
        if copy is not None:
            pytest.fail(
                f"ConfigMap '{OTHER_ORGANIZATION_NAMESPACE}/{CONFIG_MAP}' was created"
            )
    finally:
        kustomization.delete()
        namespace.delete()
