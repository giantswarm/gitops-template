"""P1-P3: what test_prune removes from what Flux applies, and the objects in it."""

import pykube
from checks.kinds import REFERENCED_KINDS
from conftest import FLUX_OBJECTS_NAMESPACE
from eso_kinds import ExternalSecretCR, PasswordCR, PushSecretCR, SecretStoreCR
from pykube.objects import APIObject
from pytest_helm_charts.flux.kustomization import KustomizationCR


class OrganizationCR(APIObject):
    version = "security.giantswarm.io/v1alpha1"
    endpoint = "organizations"
    kind = "Organization"


# What test_prune removes from the source, in the `.gitignore` format of the GitRepository's
#  `spec.ignore`. Paths start at the root of the repository. Flux's docs say `spec.ignore`
#  overrides its default exclusions, such as `.github/` and `**/.sops.yaml`; none of them
#  matches a file under a Kustomization's path here.
PRUNE_IGNORE = "\n".join(
    [
        # P2: the organisation's Organization, alone. The replacements in the organisation's
        #  kustomization.yaml take its name from it, so the organisation's directory no longer
        #  builds, and nor does the management cluster's Kustomization, which applies it.
        "/management-clusters/MC_NAME/organizations/ORG_NAME/ORG_NAME.yaml",
    ]
)
# the example's management cluster, whose GitRepository test_prune changes
MANAGEMENT_CLUSTER = "MC_NAME"
# the Kustomization of the management cluster, which applies the organization
ROOT_KUSTOMIZATION = (FLUX_OBJECTS_NAMESPACE, "mc-name-gitops")
# the organisation's namespace Kustomization, which applies the cluster's Kustomizations
ORGANIZATION_KUSTOMIZATION = (FLUX_OBJECTS_NAMESPACE, "mc-name-organization-org-name")
# the organisation's namespace, where the cluster's Kustomizations are
ORG_NAMESPACE = "org-org-name"
# the Kustomization of the out-of-band-no-flux cluster's secondary apps, which applies the app
APPS_KUSTOMIZATION = (ORG_NAMESPACE, "mc-name-clusters-out-of-band-no-flux-apps")
# the Kustomizations of the out-of-band-no-flux cluster: the cluster's, which applies the
#  cluster's HelmRelease and its base apps, and the one of its secondary apps
CLUSTER_KUSTOMIZATIONS = [
    (ORG_NAMESPACE, "mc-name-clusters-out-of-band-no-flux"),
    APPS_KUSTOMIZATION,
]
# the cluster's -direct Kustomization, which applies its out-of-band directory to the workload
#  cluster. It is in the namespace of the cluster's kubeconfig Secret, the organisation's.
DIRECT_KUSTOMIZATION = (ORG_NAMESPACE, "mc-name-clusters-out-of-band-no-flux-direct")
# P3: the cluster's application team, hello-team, which the getting-started guides remove
#  before they delete the cluster: its GitRepository and Kustomization, which the apps
#  Kustomization applies from the cluster's teams/ directory, and the team's workload, which
#  its Kustomization applies to the workload cluster as the organisation's automation
#  ServiceAccount, through a RoleBinding the -direct Kustomization applies
TEAM_OBJECTS = [
    ("GitRepository", "org-org-name", "out-of-band-no-flux-hello-team"),
    ("Kustomization", "org-org-name", "out-of-band-no-flux-hello-team"),
]
TEAM_WORKLOAD = ("hello-team", "podinfo")
# P1: an app, apps/hello-world-from-template of the out-of-band-no-flux cluster. spec.ignore can't
#  leave its directory out of the source as P2 does: apps/kustomization.yaml lists it, so the
#  apps Kustomization wouldn't build, while deleting it from Git deletes that entry too. Instead,
#  `$patch: delete` patches in the apps Kustomization's `spec.patches` drop its objects from
#  what the Kustomization builds, as deleting the directory and its entry does.
# (kind, namespace, name) of the objects of the removed app that Flux deletes
PRUNED_OBJECTS = [
    ("HelmRelease", "org-org-name", "out-of-band-no-flux-hello-world"),
    ("OCIRepository", "org-org-name", "out-of-band-no-flux-hello-world"),
    ("ConfigMap", "org-org-name", "out-of-band-no-flux-hello-world-values"),
    ("ConfigMap", "org-org-name", "out-of-band-no-flux-hello-world-user-values"),
]
# the objects in the removed files that `kustomize.toolkit.fluxcd.io/prune: disabled`
#  protects: deleting the organization deletes its clusters
PROTECTED_OBJECTS = [("Organization", "", "org-name")]
# P2: what the management cluster's Kustomization keeps, in its inventory and on the cluster,
#  when it can't build the organisation without its Organization: it prunes nothing
KEPT_BY_FAILED_BUILD = [
    *PROTECTED_OBJECTS,
    ("Kustomization", *ORGANIZATION_KUSTOMIZATION),
]
# P2: what the organisation's namespace Kustomization keeps meanwhile: it waits for the
#  management cluster's, in its `dependsOn`, so it applies and prunes nothing either
KEPT_BY_WAITING_ORGANIZATION = [
    ("Kustomization", namespace, name) for namespace, name in CLUSTER_KUSTOMIZATIONS
]
# the app's workload in the workload cluster, which goes when its HelmRelease is deleted
PRUNED_WORKLOAD = ("hello-world", "hello-world")
# the cluster's HelmRelease and OCIRepository, which deleting the cluster's Kustomization leaves
PROTECTED_CLUSTER = [
    ("HelmRelease", "org-org-name", "out-of-band-no-flux"),
    ("OCIRepository", "org-org-name", "out-of-band-no-flux"),
]
PRUNE_KINDS: dict[str, type[APIObject]] = {
    **REFERENCED_KINDS,
    "Organization": OrganizationCR,
    # the out-of-band-no-flux cluster's hello-world reads its secret values through one
    "ExternalSecret": ExternalSecretCR,
    # the out-of-band-no-flux cluster's apps push Secrets into the workload cluster with these
    "SecretStore": SecretStoreCR,
    "PushSecret": PushSecretCR,
    "Password": PasswordCR,
    # the Kustomization of the cluster's application team, hello-team
    "Kustomization": KustomizationCR,
    # what the -direct Kustomization applies to the workload cluster for the application teams
    "Namespace": pykube.Namespace,
    "ServiceAccount": pykube.ServiceAccount,
    "RoleBinding": pykube.RoleBinding,
}
# the GitRepository and the Kustomizations reconcile when asked
PRUNE_TIMEOUT_SEC = 180
# the HelmReleases uninstall their charts from the workload cluster
UNINSTALL_TIMEOUT_SEC = 300


def get_object(
    api: pykube.HTTPClient, kind: str, namespace: str, name: str
) -> dict | None:
    """The `kind` object `namespace/name`, or None if it doesn't exist. The namespace of a
    cluster-scoped object is empty."""
    query = PRUNE_KINDS[kind].objects(api)
    if namespace:
        query = query.filter(namespace=namespace)
    obj = query.get_or_none(name=name)
    return obj.obj if obj else None


def kept_problems(
    api: pykube.HTTPClient, keys: list[tuple[str, str, str]]
) -> list[str]:
    """The protected objects among `keys` that are deleted or being deleted."""
    problems = []
    for kind, namespace, name in keys:
        obj = get_object(api, kind, namespace, name)
        if obj is None:
            problems.append(f"{kind} '{namespace}/{name}' was deleted")
        elif obj["metadata"].get("deletionTimestamp"):
            problems.append(f"{kind} '{namespace}/{name}' is being deleted")
    return problems


def deleted_problems(
    api: pykube.HTTPClient, keys: list[tuple[str, str, str]]
) -> list[str]:
    """The objects among `keys` that still exist."""
    return [
        f"{kind} '{namespace}/{name}' wasn't deleted"
        for kind, namespace, name in keys
        if get_object(api, kind, namespace, name) is not None
    ]
