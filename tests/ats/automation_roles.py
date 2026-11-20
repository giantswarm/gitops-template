"""The rules of the Roles and ClusterRoles the `automation` ServiceAccounts are bound to on a Giant
Swarm management cluster, copied from their sources; automation_bindings binds them.

- giantswarm/rbac-operator at 4681152f3de2a062788baa7ecd44a2882acbce5d (RBAC_OPERATOR):
  service/controller/defaultnamespace/resource/clusterroles/create.go (the ClusterRoles) and
  service/controller/rbac/resource/automation/create.go (the shared Roles);
- giantswarm/flux-app at 02f4e84fa7a585de8e0deb95983ea47a4cbf828c (FLUX_APP):
  helm/flux-app/templates/base/clusterrole-crd-controller.yaml, which
  giantswarm/management-cluster-bases at 52aa8ee8a4ddb0c95e693bac67556150e33d956f (MC_BASES)
  renames in bases/flux-app-v2/common/kustomization.yaml.
"""

from rbac_manifests import cluster_role

RBAC_OPERATOR = "giantswarm/rbac-operator@4681152f3de2a062788baa7ecd44a2882acbce5d"
MC_BASES = (
    "giantswarm/management-cluster-bases@52aa8ee8a4ddb0c95e693bac67556150e33d956f"
)
FLUX_APP = "giantswarm/flux-app@02f4e84fa7a585de8e0deb95983ea47a4cbf828c"

READ = ["get", "list", "watch"]
WRITE = ["get", "list", "watch", "create", "update", "patch", "delete"]
ALL = ["*"]
# clusterroles/create.go isRestrictedResource, lines 441-450
RESTRICTED_RESOURCES = ("configmaps", "secrets")


def rule(groups: list[str], resources: list[str], verbs: list[str]) -> dict:
    return {"apiGroups": groups, "resources": resources, "verbs": verbs}


# clusterroles/create.go lines 126-131
POD_LOGS_RULE = rule([""], ["pods/log"], ["get", "list"])


def read_all_rules(discovery: list[dict]) -> list[dict]:
    """The rules of `read-all`: get, list and watch on every resource the API server serves,
    except ConfigMaps and Secrets, and get and list on `pods/log`.

    rbac-operator builds them from discovery (clusterroles/create.go createReadAllClusterRole,
    lines 88-148), with client-go's ServerPreferredResources: one rule per group and resource,
    from its preferred version, without subresources. It then skips the resources without
    verbs, so one the preferred version serves without verbs gets no rule. `discovery` holds
    the APIResourceLists, the preferred version of each group first.
    """
    rules = []
    seen = set()
    for resource_list in discovery:
        group = resource_list["groupVersion"].rpartition("/")[0]
        for resource in resource_list.get("resources") or []:
            name = resource["name"]
            if "/" in name or (group, name) in seen:
                continue
            seen.add((group, name))
            if resource.get("verbs") and name not in RESTRICTED_RESOURCES:
                rules.append(rule([group], [name], READ))
    rules.append(POD_LOGS_RULE)
    return rules


# FLUX_APP clusterrole-crd-controller.yaml with podSecurityStandards enforced, so without the
#  PodSecurityPolicy rule
FLUX_GROUPS = [
    "source.toolkit.fluxcd.io",
    "kustomize.toolkit.fluxcd.io",
    "helm.toolkit.fluxcd.io",
    "notification.toolkit.fluxcd.io",
    "image.toolkit.fluxcd.io",
    "source.extensions.fluxcd.io",
]
CRD_CONTROLLER_RULES = [rule([group], ["*"], ALL) for group in FLUX_GROUPS] + [
    rule([""], ["namespaces", "secrets", "configmaps", "serviceaccounts"], READ),
    rule([""], ["events"], ["create", "patch"]),
    rule([""], ["configmaps"], WRITE),
    rule([""], ["configmaps/status"], ["get", "update", "patch"]),
    rule(["coordination.k8s.io"], ["leases"], WRITE),
    rule([""], ["serviceaccounts/token"], ["create"]),
    {"nonResourceURLs": ["/livez/ping"], "verbs": ["head"]},
]

# The ClusterRoles other than `read-all`, with the lines of clusterroles/create.go they come
#  from. `cluster-admin` is Kubernetes' own. `kamaji-datastore-manager` comes from the Kamaji
#  app, which the kind cluster doesn't run, so its bindings grant nothing, as on a management
#  cluster without Kamaji.
STATIC_CLUSTER_ROLES = {
    # lines 154-177
    "write-organizations": [rule(["security.giantswarm.io"], ["organizations"], ALL)],
    # lines 233-259
    "write-client-certificates": [rule(["core.giantswarm.io"], ["certconfigs"], ALL)],
    # lines 265-291
    "write-silences": [rule(["monitoring.giantswarm.io"], ["silences"], ALL)],
    # lines 297-323
    "write-policy-exceptions": [rule(["kyverno.io"], ["policyexceptions"], ALL)],
    # lines 329-351: on CAPA management clusters, which the template's cluster examples are
    "write-aws-cluster-role-identity": [
        rule(["infrastructure.cluster.x-k8s.io"], ["awsclusterroleidentities"], ALL)
    ],
    # lines 357-392
    "cluster-app-chart-lookups": [
        rule(["release.giantswarm.io"], ["releases"], READ),
        rule([""], ["nodes"], READ),
        rule(["infrastructure.cluster.x-k8s.io"], ["awsclusterroleidentities"], READ),
    ],
    # FLUX_APP's `crd-controller`, under the name MC_BASES gives it
    "crd-controller-giantswarm": CRD_CONTROLLER_RULES,
}

# rbac/resource/automation/create.go lines 154-175
PATCH_CHARTS_RULES = [
    rule(["application.giantswarm.io"], ["charts"], ["list", "get", "patch"])
]
WRITE_POLICY_EXCEPTIONS_RULES = STATIC_CLUSTER_ROLES["write-policy-exceptions"]
# MC_BASES bases/flux-app-v2/common/resource-rbac.yaml lines 34-46
READ_PODS_AND_LOGS_RULES = [rule([""], ["pods", "pods/log"], ["get", "list"])]


def cluster_roles(read_all: list[dict]) -> list[dict]:
    """Every ClusterRole the `automation` ServiceAccounts are bound to, but `cluster-admin`."""
    return [cluster_role("read-all", read_all)] + [
        cluster_role(name, rules) for name, rules in STATIC_CLUSTER_ROLES.items()
    ]
