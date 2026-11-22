"""A stand-in for organization-operator and the operators that fill an organisation's namespace
on a Giant Swarm management cluster, which the kind cluster doesn't run.

The kind test bootstraps the repository as a new management cluster does: no `Organization` and
no `org-*` namespace exist before Flux applies the root Kustomization, `mc-name-gitops`. The
root applies the `Organization`, and the organisation's namespace Kustomization, which fails
until the namespace exists. The stand-in then does what the management cluster does: it creates
the namespace, as organization-operator does for the `Organization`, and in it what the other
operators create, such as `automation` and its rights (rbac-operator). The organisation's
Kustomization has to get ready on its own next retry, without being asked to reconcile. The
workload clusters' Kustomizations are in workload-clusters/, which its namespace/ lists, so they
appear only then, and run as the organisation's `automation`.
"""

import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pykube
import pytest
from automation_rbac import organization_rbac
from checks.conditions import is_ready, not_ready_reason, obj_key
from conftest import (
    CLUSTER_VALUES_STUB,
    WORKLOAD_CLUSTER_VALUES_NAME,
    WORKLOAD_CLUSTER_VCLUSTER_NAME,
    VCluster,
    apply,
    installation_values_config_map,
)
from external_secrets import organization_store
from flux_reconcile import wait_until
from notification_objects import organization_alert
from prune_objects import OrganizationCR
from pykube.objects import APIObject
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.kustomization import KustomizationCR
from workload_cluster_kubeconfig_push import TOOLS_CLUSTER, cluster_kubeconfig_secret

ORGANIZATION = "org-name"
ORG_NAMESPACE = f"org-{ORGANIZATION}"
FLUX_NAMESPACE = "default"
ROOT_KUSTOMIZATION = "mc-name-gitops"
# organizations/ORG_NAME/namespace.yaml, which applies namespace/ into ORG_NAMESPACE
ORGANIZATION_KUSTOMIZATION = "mc-name-organization-org-name"
# the label Flux puts on what a Kustomization applies, naming the Kustomization
OWNER_LABEL = "kustomize.toolkit.fluxcd.io/name"
# the GitRepository has to fetch the repository before the root applies anything
ORGANIZATION_TIMEOUT_SEC = 300
# the organisation's Kustomization runs once the root has created it
WAITING_TIMEOUT_SEC = 120
# Flux retries a failed Kustomization after its `retryInterval`, 1m: two of them and a margin
RECOVERY_TIMEOUT_SEC = 150

# What the stand-in creates in the namespace once it exists: each takes the test cluster's
#  client and the namespace, and returns the objects it created.
NamespaceSetup = Callable[[pykube.HTTPClient, str], list[pykube.objects.APIObject]]

logger = logging.getLogger(__name__)


def bootstrapped_problems(
    organization: dict | None, namespace: dict | None
) -> list[str]:
    """What exists already that a new management cluster doesn't have."""
    problems = []
    if organization is not None:
        problems.append(f"Organization '{ORGANIZATION}' exists before the bootstrap")
    if namespace is not None:
        problems.append(f"Namespace '{ORG_NAMESPACE}' exists before the bootstrap")
    return problems


def organization_problems(organization: dict | None) -> list[str]:
    """Why the Organization isn't one the root Kustomization applied, if it isn't."""
    if organization is None:
        return [f"Flux hasn't created Organization '{ORGANIZATION}'"]
    owner = (organization["metadata"].get("labels") or {}).get(OWNER_LABEL)
    if owner != ROOT_KUSTOMIZATION:
        return [
            f"Organization '{ORGANIZATION}' isn't applied by '{ROOT_KUSTOMIZATION}' "
            f"but by '{owner}'"
        ]
    return []


def ready_problems(kustomization: dict | None, name: str) -> list[str]:
    """Why the Kustomization `name` isn't Ready, if it isn't."""
    if kustomization is None:
        return [f"Kustomization '{name}' doesn't exist"]
    if is_ready(kustomization):
        return []
    return [
        f"Kustomization '{obj_key(kustomization)}' isn't ready: "
        f"{not_ready_reason(kustomization)}"
    ]


def root_problems(root: dict | None) -> list[str]:
    """Why the root Kustomization isn't Ready, if it isn't."""
    return ready_problems(root, ROOT_KUSTOMIZATION)


def waiting_problems(kustomization: dict | None) -> list[str]:
    """Why the organisation's Kustomization doesn't fail for want of the namespace, if it
    doesn't. Flux names the namespace in its error: it doesn't exist, or `automation` may not
    write there, as rbac-operator gives it its rights in the namespace only once it exists.
    """
    if kustomization is None:
        return [f"Kustomization '{ORGANIZATION_KUSTOMIZATION}' doesn't exist"]
    key = obj_key(kustomization)
    if is_ready(kustomization):
        return [f"Kustomization '{key}' is Ready without namespace '{ORG_NAMESPACE}'"]
    reason = not_ready_reason(kustomization)
    if f'"{ORG_NAMESPACE}"' in reason:
        return []
    return [
        f"Kustomization '{key}' doesn't wait for namespace '{ORG_NAMESPACE}': {reason}"
    ]


def _get(
    api: pykube.HTTPClient, kind: type[APIObject], name: str, namespace: str = ""
) -> dict | None:
    objects = kind.objects(api)
    if namespace:
        objects = objects.filter(namespace=namespace)
    obj = objects.get_or_none(name=name)
    return obj.obj if obj is not None else None


def _kustomization(api: pykube.HTTPClient, name: str) -> dict | None:
    return _get(api, KustomizationCR, name, FLUX_NAMESPACE)


@pytest.fixture(scope="module")
def no_organization_before_bootstrap(kube_cluster: Cluster) -> None:
    """Fail if the Organization or its namespace exist before Flux applies the repository."""
    api = kube_cluster.kube_client
    problems = bootstrapped_problems(
        _get(api, OrganizationCR, ORGANIZATION),
        _get(api, pykube.Namespace, ORG_NAMESPACE),
    )
    if problems:
        pytest.fail("\n".join(problems))


def create_namespace(
    api: pykube.HTTPClient,
    setups: list[NamespaceSetup],
    created: list[pykube.objects.APIObject],
) -> None:
    """Create the organisation's namespace, then what each of `setups` creates in it. Add
    everything to `created` as it goes, the namespace first, so it's deleted also when a setup
    fails."""
    namespace = pykube.Namespace(api, {"metadata": {"name": ORG_NAMESPACE}})
    namespace.create()
    created.append(namespace)
    for setup in setups:
        created += setup(api, ORG_NAMESPACE)


@pytest.fixture(scope="module")
def organization_operator(
    kube_cluster: Cluster,
    gitops_root: None,
    organization_namespace_setups: list[NamespaceSetup],
    organization_objects: list[pykube.objects.APIObject],
) -> Iterator[None]:
    """Wait for Flux to create the Organization, then create its namespace and what the
    management cluster creates in it, and wait for the organisation's Kustomization to get ready
    on its own retry. What it creates goes into `organization_objects`, which deletes it once
    the repository's Kustomizations are gone."""
    api = kube_cluster.kube_client
    wait_until(
        lambda: organization_problems(_get(api, OrganizationCR, ORGANIZATION))
        + root_problems(_kustomization(api, ROOT_KUSTOMIZATION)),
        ORGANIZATION_TIMEOUT_SEC,
        "the root Kustomization didn't apply the Organization",
    )
    wait_until(
        lambda: waiting_problems(_kustomization(api, ORGANIZATION_KUSTOMIZATION)),
        WAITING_TIMEOUT_SEC,
        "the organisation's Kustomization doesn't wait for its namespace",
    )
    logger.info(
        f"Kustomization '{ORGANIZATION_KUSTOMIZATION}' waits for its namespace: "
        f"{not_ready_reason(_kustomization(api, ORGANIZATION_KUSTOMIZATION) or {})}"
    )

    started = time.monotonic()
    create_namespace(api, organization_namespace_setups, organization_objects)
    wait_until(
        lambda: ready_problems(
            _kustomization(api, ORGANIZATION_KUSTOMIZATION), ORGANIZATION_KUSTOMIZATION
        ),
        RECOVERY_TIMEOUT_SEC,
        "the organisation's Kustomization didn't recover on its own retry",
    )
    logger.info(
        f"Kustomization '{ORGANIZATION_KUSTOMIZATION}' got ready "
        f"{time.monotonic() - started:.0f} s after its namespace was created"
    )
    yield None


def installation_values(
    api: pykube.HTTPClient, namespace: str
) -> list[pykube.objects.APIObject]:
    """Create the stand-in `cluster-app-installation-values` in the organisation's `namespace`,
    as the management cluster's Kyverno policy copies it there."""
    return [apply(installation_values_config_map(api, namespace))]


def workload_cluster_objects(
    api: pykube.HTTPClient, namespace: str, kubeconfig: dict
) -> list[pykube.objects.APIObject]:
    """Create in the organisation's `namespace` what the management cluster has there for the
    workload cluster: its kubeconfig Secret, as Cluster API writes it, and its cluster values,
    as cluster-apps-operator writes them. The kubeconfig Secret of the cluster the
    out-of-band-no-flux apps push their kubeconfig to has the vCluster's kubeconfig too: the
    vCluster stands in for both clusters."""
    cluster_values = pykube.ConfigMap(
        api,
        {
            "metadata": {"name": WORKLOAD_CLUSTER_VALUES_NAME, "namespace": namespace},
            "data": {"values": Path(CLUSTER_VALUES_STUB).read_text()},
        },
    )
    kubeconfig_secrets = [
        pykube.Secret(api, cluster_kubeconfig_secret(cluster, namespace, kubeconfig))
        for cluster in (WORKLOAD_CLUSTER_VCLUSTER_NAME, TOOLS_CLUSTER)
    ]
    return [apply(cluster_values)] + [apply(s) for s in kubeconfig_secrets]


@pytest.fixture(scope="module")
def organization_objects(
    external_secrets: None,
    workload_cluster: pykube.HTTPClient,
    automation_rbac: None,
) -> Iterator[list[pykube.objects.APIObject]]:
    """What organization_operator creates in the organisation's namespace, and the namespace
    itself. They're deleted, the namespace last, once the repository's Kustomizations are gone,
    and before the fixtures this one depends on remove what they installed."""
    created: list[pykube.objects.APIObject] = []

    yield created

    for obj in reversed(created):
        if obj.exists():
            obj.delete()


@pytest.fixture(scope="module")
def organization_namespace_setups(
    kube_cluster: Cluster, vcluster: VCluster
) -> list[NamespaceSetup]:
    """What organization_operator creates in the organisation's namespace once it exists, in
    order, as the management cluster's operators do: the organisation's Alert, suspended before
    Flux applies it; `automation` and its rights (rbac-operator); the installation values
    (Kyverno); the test's secret store; the workload cluster's kubeconfig Secret and cluster
    values (Cluster API and cluster-apps-operator)."""
    return [
        lambda api, namespace: organization_alert(kube_cluster, namespace),
        organization_rbac,
        installation_values,
        organization_store,
        lambda api, namespace: workload_cluster_objects(
            api, namespace, vcluster.kubeconfig
        ),
    ]


@pytest.fixture(scope="module")
def gitops_deployment(organization_operator: None) -> None:
    """The repository bootstrapped as on a new management cluster: Flux has applied the root
    Kustomization, and the organisation's namespace Kustomization is ready, once
    organization_operator has created the namespace."""
