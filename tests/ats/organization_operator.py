"""A stand-in for organization-operator and the operators that fill an organisation's namespace
on a Giant Swarm management cluster, which the kind cluster doesn't run.

The kind test bootstraps the repository as a new management cluster does: no `Organization` and
no `org-*` namespace exist before Flux applies the root Kustomizations. The roots apply the
`Organization`s, and each organisation's namespace Kustomization, which fails until the namespace
exists. The stand-in then does what the management cluster does, for every `Organization`: it
creates the namespace, as organization-operator does, and in it what the other operators create,
such as `automation` and its rights (rbac-operator). Each Kustomization that applies into the
namespace has to get ready on its own next retry, without being asked to reconcile. The workload
clusters' Kustomizations are in the organisation's workload-clusters/, which its namespace/
lists, so they appear only then, and run as the organisation's `automation`.

Nothing here names an organisation: the stand-in works on whatever Organizations the roots apply.
"""

import logging
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pykube
import pytest
from automation_rbac import organization_rbac
from checks import waits
from checks.conditions import is_ready, not_ready_reason, obj_key
from conftest import (
    CLUSTER_VALUES_STUB,
    WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE,
    WORKLOAD_CLUSTER_VALUES_NAME,
    WORKLOAD_CLUSTER_VCLUSTER_NAME,
    VCluster,
    apply,
    installation_values_config_map,
)
from external_secrets import organization_store
from flux_inventory import DEPENDENCY_NOT_READY
from flux_reconcile import wait_until
from kind_config import kind_test_config
from notification_objects import organization_alert
from prune_objects import OrganizationCR
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.kustomization import KustomizationCR
from workload_cluster_kubeconfig_push import (
    EXAMPLE as KUBECONFIG_PUSH_EXAMPLE,
)
from workload_cluster_kubeconfig_push import (
    TOOLS_CLUSTER,
    cluster_kubeconfig_secret,
)

ORG_NAMESPACE_PREFIX = "org-"
# the GitRepositories have to fetch the repository before the roots apply anything
ROOTS_TIMEOUT_SEC = 300
# an organisation's Kustomization runs once the root has created it
WAITING_TIMEOUT_SEC = 120
# Flux retries a failed Kustomization after its `retryInterval`, 1m: two of them and a margin
RECOVERY_TIMEOUT_SEC = 150

# What the stand-in creates in a namespace once it exists: each takes the test cluster's
#  client and the namespace, and returns the objects it created.
NamespaceSetup = Callable[[pykube.HTTPClient, str], list[pykube.objects.APIObject]]

logger = logging.getLogger(__name__)


def organization_namespace(organization: str) -> str:
    """The namespace organization-operator creates for the Organization `organization`."""
    return f"{ORG_NAMESPACE_PREFIX}{organization}"


def bootstrapped_problems(organizations: list[str], namespaces: list[str]) -> list[str]:
    """What exists already that a new management cluster doesn't have: any Organization, or
    any organisation namespace."""
    return [
        f"Organization '{o}' exists before the bootstrap" for o in organizations
    ] + [
        f"Namespace '{n}' exists before the bootstrap"
        for n in namespaces
        if n.startswith(ORG_NAMESPACE_PREFIX)
    ]


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


def waiting_kustomizations(kustomizations: list[dict], namespace: str) -> list[dict]:
    """The Kustomizations among `kustomizations` that apply into `namespace` from another one,
    such as an organisation's namespace Kustomization in `default`: they wait for it."""
    return [
        k
        for k in kustomizations
        if (k.get("spec") or {}).get("targetNamespace") == namespace
        and k["metadata"].get("namespace") != namespace
    ]


def _ready_reason(kustomization: dict) -> str | None:
    conditions = (kustomization.get("status") or {}).get("conditions") or []
    return next((c.get("reason") for c in conditions if c.get("type") == "Ready"), None)


def waiting_problems(kustomization: dict, namespace: str) -> list[str]:
    """Why the Kustomization doesn't fail for want of `namespace`, if it doesn't. Flux names the
    namespace in its error: it doesn't exist, or `automation` may not write there, as
    rbac-operator gives it its rights in the namespace only once it exists.
    """
    key = obj_key(kustomization)
    if is_ready(kustomization):
        return [f"Kustomization '{key}' is Ready without namespace '{namespace}'"]
    reason = not_ready_reason(kustomization)
    if f'"{namespace}"' in reason:
        return []
    return [f"Kustomization '{key}' doesn't wait for namespace '{namespace}': {reason}"]


def _depends_on_one_of(kustomization: dict, keys: set[str]) -> bool:
    own = kustomization["metadata"].get("namespace", "default")
    return any(
        f"{d.get('namespace', own)}/{d.get('name')}" in keys
        for d in (kustomization.get("spec") or {}).get("dependsOn") or []
    )


def namespace_waiting_problems(kustomizations: list[dict], namespace: str) -> list[str]:
    """Why the Kustomizations among `kustomizations` that apply into `namespace` don't all wait
    for it, if they don't: each fails for want of it, or reports DependencyNotReady on another
    of them. There has to be at least one, or nothing shows the namespace is awaited."""
    waiting = waiting_kustomizations(kustomizations, namespace)
    if not waiting:
        return [
            f"No Kustomization applies into namespace '{namespace}' from another namespace, so "
            "the stand-in can't tell that the Organization's namespace is awaited: give the "
            f"organisation a namespace Kustomization with `targetNamespace: {namespace}`, as "
            "the basic tutorial does"
        ]
    keys = {obj_key(k) for k in waiting}
    return [
        p
        for k in waiting
        if not (
            _ready_reason(k) == DEPENDENCY_NOT_READY and _depends_on_one_of(k, keys)
        )
        for p in waiting_problems(k, namespace)
    ]


def _kustomizations(api: pykube.HTTPClient) -> dict[str, dict]:
    return waits.list_objects(api, KustomizationCR, ())


def _organizations(api: pykube.HTTPClient) -> list[str]:
    return sorted(o.name for o in OrganizationCR.objects(api))


def _roots_problems(api: pykube.HTTPClient) -> list[str]:
    kustomizations = _kustomizations(api)
    return [
        p
        for root in kind_test_config().roots()
        for p in ready_problems(
            kustomizations.get(f"{root.namespace}/{root.name}"), root.name
        )
    ]


@pytest.fixture(scope="module")
def no_organization_before_bootstrap(kube_cluster: Cluster) -> None:
    """Fail if an Organization or an organisation namespace exists before Flux applies the
    repository."""
    api = kube_cluster.kube_client
    problems = bootstrapped_problems(
        _organizations(api), [n.name for n in pykube.Namespace.objects(api)]
    )
    if problems:
        pytest.fail("\n".join(problems))


def create_namespace(
    api: pykube.HTTPClient,
    namespace: str,
    setups: list[NamespaceSetup],
    created: list[pykube.objects.APIObject],
) -> None:
    """Create the organisation's `namespace`, then what each of `setups` creates in it. Add
    everything to `created` as it goes, the namespace first, so it's deleted also when a setup
    fails."""
    ns = pykube.Namespace(api, {"metadata": {"name": namespace}})
    ns.create()
    created.append(ns)
    for setup in setups:
        created += setup(api, namespace)


def _waiting(api: pykube.HTTPClient, namespace: str) -> list[dict]:
    return waiting_kustomizations(list(_kustomizations(api).values()), namespace)


def _waiting_problems(api: pykube.HTTPClient, namespace: str) -> list[str]:
    return namespace_waiting_problems(list(_kustomizations(api).values()), namespace)


def _recovery_problems(api: pykube.HTTPClient, namespace: str) -> list[str]:
    waiting = _waiting(api, namespace)
    if not waiting:
        return [f"No Kustomization applies into namespace '{namespace}' any more"]
    return [p for k in waiting for p in ready_problems(k, obj_key(k))]


def stand_in_for(
    api: pykube.HTTPClient,
    namespace: str,
    setups: list[NamespaceSetup],
    created: list[pykube.objects.APIObject],
) -> None:
    """Wait for the Kustomizations that apply into the organisation's `namespace` to fail for
    want of it, create it with what `setups` create in it, and wait for them to get ready on
    their own retry."""
    wait_until(
        lambda: _waiting_problems(api, namespace),
        WAITING_TIMEOUT_SEC,
        f"the Kustomizations of '{namespace}' don't wait for it",
    )
    waiting = [obj_key(k) for k in _waiting(api, namespace)]
    logger.info(f"Kustomizations {waiting} wait for namespace '{namespace}'")

    started = time.monotonic()
    create_namespace(api, namespace, setups, created)
    wait_until(
        lambda: _recovery_problems(api, namespace),
        RECOVERY_TIMEOUT_SEC,
        f"the Kustomizations of '{namespace}' didn't recover on their own retry",
    )
    logger.info(
        f"Kustomizations {waiting} got ready {time.monotonic() - started:.0f} s after "
        f"namespace '{namespace}' was created"
    )


@pytest.fixture(scope="module")
def organization_operator(
    kube_cluster: Cluster,
    gitops_root: None,
    organization_namespace_setups: list[NamespaceSetup],
    organization_objects: list[pykube.objects.APIObject],
) -> Iterator[list[str]]:
    """Wait for the roots to apply the Organizations, then create each one's namespace and what
    the management cluster creates in it, and wait for the Kustomizations that apply into it to
    get ready on their own retry. Yields the namespaces. What it creates goes into
    `organization_objects`, which deletes it once the repository's Kustomizations are gone.
    """
    api = kube_cluster.kube_client
    wait_until(
        lambda: _roots_problems(api),
        ROOTS_TIMEOUT_SEC,
        "the root Kustomizations aren't ready",
    )
    namespaces = [organization_namespace(o) for o in _organizations(api)]
    logger.info(f"The roots applied the Organizations of {namespaces}")
    for namespace in namespaces:
        stand_in_for(
            api, namespace, organization_namespace_setups, organization_objects
        )
    yield namespaces


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
    out-of-band-no-flux apps push their kubeconfig to has the vCluster's kubeconfig too, when that
    example is there: the vCluster stands in for both clusters."""
    cluster_values = pykube.ConfigMap(
        api,
        {
            "metadata": {"name": WORKLOAD_CLUSTER_VALUES_NAME, "namespace": namespace},
            "data": {"values": Path(CLUSTER_VALUES_STUB).read_text()},
        },
    )
    clusters = [WORKLOAD_CLUSTER_VCLUSTER_NAME]
    if not kind_test_config().example_skip_reason(KUBECONFIG_PUSH_EXAMPLE):
        clusters.append(TOOLS_CLUSTER)
    kubeconfig_secrets = [
        pykube.Secret(api, cluster_kubeconfig_secret(cluster, namespace, kubeconfig))
        for cluster in clusters
    ]
    return [apply(cluster_values)] + [apply(s) for s in kubeconfig_secrets]


@pytest.fixture(scope="module")
def organization_objects(
    external_secrets: None,
    optional_vcluster: VCluster | None,
    automation_rbac: None,
) -> Iterator[list[pykube.objects.APIObject]]:
    """What organization_operator creates in the organisations' namespaces, and the namespaces
    themselves. They're deleted, the namespaces last, once the repository's Kustomizations are
    gone, and before the fixtures this one depends on remove what they installed."""
    created: list[pykube.objects.APIObject] = []

    yield created

    for obj in reversed(created):
        if obj.exists():
            obj.delete()


@pytest.fixture(scope="module")
def organization_namespace_setups(
    kube_cluster: Cluster, optional_vcluster: VCluster | None
) -> list[NamespaceSetup]:
    """What organization_operator creates in each organisation's namespace once it exists, in
    order, as the management cluster's operators do: `automation` and its rights
    (rbac-operator); the installation values (Kyverno); the stand-in secret store, if
    kind-test.yaml has one. For the template's examples, when they're there: the notification
    example's Alert, suspended before Flux applies it, and the vCluster's kubeconfig Secret and
    cluster values (Cluster API and cluster-apps-operator) in its organisation's namespace.
    """

    def example_objects(
        api: pykube.HTTPClient, namespace: str
    ) -> list[pykube.objects.APIObject]:
        if (
            optional_vcluster is None
            or namespace != WORKLOAD_CLUSTER_KUBECONFIG_NAMESPACE
        ):
            return []
        return workload_cluster_objects(api, namespace, optional_vcluster.kubeconfig)

    return [
        lambda api, namespace: organization_alert(kube_cluster, namespace),
        organization_rbac,
        installation_values,
        organization_store,
        example_objects,
    ]


@pytest.fixture(scope="module")
def gitops_deployment(organization_operator: list[str]) -> list[str]:
    """The repository bootstrapped as on a new management cluster: Flux has applied the root
    Kustomizations, and the organisations' namespace Kustomizations are ready, once
    organization_operator has created the namespaces. Returns the organisations' namespaces.
    """
    return organization_operator
