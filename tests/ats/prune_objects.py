"""P1, P2: the files test_prune removes from the source, and the objects in them.

prune_checks imports this module, which imports test_flux_objects, which imports prune_checks on
its last line: import test_flux_objects, not this module.
"""

import pykube
from conftest import FLUX_OBJECTS_NAMESPACE
from pykube.objects import APIObject
from test_flux_objects import REFERENCED_KINDS


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
        # P1: an app, the hello-web-app-1 app set of the out-of-band-no-flux cluster
        "/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/"
        "WC_NAME_OUT_OF_BAND_NO_FLUX_APP/mapi/app_sets/hello-web-app-1/",
        # P2: the organization
        "/management-clusters/MC_NAME/organizations/ORG_NAME/ORG_NAME.yaml",
    ]
)
# the Kustomization of the management cluster, which applies the organization
ROOT_KUSTOMIZATION = (FLUX_OBJECTS_NAMESPACE, "mc-name-gitops")
# the Kustomization of the out-of-band-no-flux cluster, which applies the app set
CLUSTER_KUSTOMIZATION = (FLUX_OBJECTS_NAMESPACE, "mc-name-clusters-out-of-band-no-flux")
# (kind, namespace, name) of the objects in the removed files that Flux deletes: the app
PRUNED_OBJECTS = [
    ("HelmRelease", "org-org-name", "out-of-band-no-flux-hello-world"),
    ("OCIRepository", "org-org-name", "out-of-band-no-flux-hello-world"),
    ("ConfigMap", "org-org-name", "out-of-band-no-flux-hello-world-values"),
    ("ConfigMap", "org-org-name", "out-of-band-no-flux-hello-world-user-values"),
]
# the objects in the removed files that `kustomize.toolkit.fluxcd.io/prune: disabled`
#  protects: deleting the organization deletes its clusters
PROTECTED_OBJECTS = [("Organization", "", "org-name")]
# the app's workload in the workload cluster, which goes when its HelmRelease is deleted
PRUNED_WORKLOAD = ("org-org-name", "hello-world")
# the cluster's HelmRelease, which deleting the cluster's Kustomization leaves
PROTECTED_CLUSTER = ("HelmRelease", "org-org-name", "out-of-band-no-flux")
PRUNE_KINDS: dict[str, type[APIObject]] = {
    **REFERENCED_KINDS,
    "Organization": OrganizationCR,
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
