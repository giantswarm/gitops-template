"""The Kyverno policies that decide whether a management cluster admits a Flux object.

Every Giant Swarm management cluster runs two `ClusterPolicy`s from management-cluster-bases:
`flux-multi-tenancy`, on Flux's own kinds, and `flux-operator-multi-tenancy`, on Flux Operator's.
Outside `flux-giantswarm`, `giantswarm` and `monitoring`, a `Kustomization` or `HelmRelease` needs
`serviceAccountName` or a kubeconfig, keeps its target and storage namespace and its sources in
its own namespace or `default`, and a `ResourceSet` needs `serviceAccountName`. Both refuse what
breaks a rule: `validationFailureAction: Enforce`.

fixtures/admission-policies holds them, copied at SOURCE_COMMIT and only re-indented, as
automation_roles holds rbac-operator's rules. The `admission_policies` fixture applies them once Kyverno runs and
before Flux applies the repository, so an example the management cluster would refuse at
admission fails the kind test too.
"""

import logging
import time
from collections.abc import Iterator
from pathlib import Path

import pykube
import pytest
import yaml
from conftest import apply
from pykube.objects import APIObject
from pytest_helm_charts.clusters import Cluster

SOURCE_COMMIT = "54ec7bdb049a14d343999107abe7174cb65fd9f2"
POLICIES_DIR = Path(__file__).resolve().parent / "fixtures" / "admission-policies"
# Kyverno configures its webhook for a new policy within seconds
POLICY_READY_TIMEOUT_SEC = 120

logger = logging.getLogger(__name__)


class ClusterPolicy(APIObject):
    version = "kyverno.io/v1"
    endpoint = "clusterpolicies"
    kind = "ClusterPolicy"


def load_policies() -> list[dict]:
    """The policies in POLICIES_DIR, in file order."""
    policies = []
    for file in sorted(POLICIES_DIR.glob("*.yaml")):
        with file.open() as f:
            policies += [doc for doc in yaml.safe_load_all(f) if doc]
    return policies


def ready_problems(policy: dict) -> list[str]:
    """Why the policy isn't Ready, if it isn't: until it is, Kyverno may admit what it refuses."""
    name = policy["metadata"]["name"]
    conditions = (policy.get("status") or {}).get("conditions") or []
    ready = next((c for c in conditions if c.get("type") == "Ready"), None)
    if ready is None:
        return [f"ClusterPolicy '{name}' isn't ready: no Ready condition yet"]
    if ready.get("status") == "True":
        return []
    return [
        f"ClusterPolicy '{name}' isn't ready: "
        f"{ready.get('reason')}: {ready.get('message', '')}"
    ]


@pytest.fixture(scope="module")
def admission_policies(kube_cluster: Cluster, kyverno: None) -> Iterator[None]:
    """Apply the policies and wait until Kyverno enforces them. They stay: the test cluster goes
    away with them."""
    api: pykube.HTTPClient = kube_cluster.kube_client
    names = [apply(ClusterPolicy(api, p)).name for p in load_policies()]
    deadline = time.monotonic() + POLICY_READY_TIMEOUT_SEC
    while True:
        problems = [
            p
            for name in names
            for p in ready_problems(ClusterPolicy.objects(api).get(name=name).obj)
        ]
        if not problems:
            break
        if time.monotonic() >= deadline:
            pytest.fail("\n".join(problems))
        time.sleep(2)
    logger.info(f"Kyverno enforces {names}")
    yield
