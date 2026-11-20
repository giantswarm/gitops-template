"""The rules of the Roles and ClusterRoles the `automation` ServiceAccounts are bound to on a Giant
Swarm management cluster, copied from their sources; automation_rbac binds them.

- giantswarm/rbac-operator at 4681152f3de2a062788baa7ecd44a2882acbce5d (RBAC_OPERATOR):
  service/controller/defaultnamespace/resource/clusterroles/create.go (the ClusterRoles) and
  service/controller/rbac/resource/automation/create.go (the shared Roles);
- giantswarm/flux-app at 02f4e84fa7a585de8e0deb95983ea47a4cbf828c (FLUX_APP):
  helm/flux-app/templates/base/clusterrole-crd-controller.yaml, which
  giantswarm/management-cluster-bases at 52aa8ee8a4ddb0c95e693bac67556150e33d956f (MC_BASES)
  renames in bases/flux-app-v2/common/kustomization.yaml.
"""

RBAC_OPERATOR = "giantswarm/rbac-operator@4681152f3de2a062788baa7ecd44a2882acbce5d"
MC_BASES = (
    "giantswarm/management-cluster-bases@52aa8ee8a4ddb0c95e693bac67556150e33d956f"
)
FLUX_APP = "giantswarm/flux-app@02f4e84fa7a585de8e0deb95983ea47a4cbf828c"

MANAGED_BY = {"giantswarm.io/managed-by": "rbac-operator"}
READ = ["get", "list", "watch"]
ALL_CONFIGMAP_VERBS = ["get", "list", "watch", "create", "update", "patch", "delete"]
# clusterroles/create.go isRestrictedResource, lines 441-450
RESTRICTED_RESOURCES = ("configmaps", "secrets")
# clusterroles/create.go lines 126-131
POD_LOGS_RULE = {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]}


def all_verbs(group: str, resource: str) -> list[dict]:
    return [{"apiGroups": [group], "resources": [resource], "verbs": ["*"]}]


def read_all_rules(discovery: list[dict]) -> list[dict]:
    """The rules of `read-all`: get, list and watch on every resource the API server serves,
    except ConfigMaps and Secrets, and get and list on `pods/log`.

    rbac-operator builds them from discovery (clusterroles/create.go createReadAllClusterRole,
    lines 88-148), with client-go's ServerPreferredResources: one rule per group and resource,
    whatever the version, without subresources and resources without verbs. `discovery` holds
    the APIResourceLists, the preferred version of each group first.
    """
    rules = []
    seen = set()
    for resource_list in discovery:
        group = resource_list["groupVersion"].rpartition("/")[0]
        for resource in resource_list.get("resources") or []:
            name = resource["name"]
            skip = "/" in name or not resource.get("verbs")
            if skip or name in RESTRICTED_RESOURCES or (group, name) in seen:
                continue
            seen.add((group, name))
            rules.append({"apiGroups": [group], "resources": [name], "verbs": READ})
    rules.append(POD_LOGS_RULE)
    return rules


# FLUX_APP clusterrole-crd-controller.yaml with podSecurityStandards enforced, so without the
#  PodSecurityPolicy rule
CRD_CONTROLLER_RULES = [
    {"apiGroups": [group], "resources": ["*"], "verbs": ["*"]}
    for group in [
        "source.toolkit.fluxcd.io",
        "kustomize.toolkit.fluxcd.io",
        "helm.toolkit.fluxcd.io",
        "notification.toolkit.fluxcd.io",
        "image.toolkit.fluxcd.io",
        "source.extensions.fluxcd.io",
    ]
] + [
    {
        "apiGroups": [""],
        "resources": ["namespaces", "secrets", "configmaps", "serviceaccounts"],
        "verbs": READ,
    },
    {"apiGroups": [""], "resources": ["events"], "verbs": ["create", "patch"]},
    {"apiGroups": [""], "resources": ["configmaps"], "verbs": ALL_CONFIGMAP_VERBS},
    {
        "apiGroups": [""],
        "resources": ["configmaps/status"],
        "verbs": ["get", "update", "patch"],
    },
    {
        "apiGroups": ["coordination.k8s.io"],
        "resources": ["leases"],
        "verbs": ALL_CONFIGMAP_VERBS,
    },
    {"apiGroups": [""], "resources": ["serviceaccounts/token"], "verbs": ["create"]},
    {"nonResourceURLs": ["/livez/ping"], "verbs": ["head"]},
]

# The ClusterRoles other than `read-all`, with the lines of clusterroles/create.go they come
#  from. `cluster-admin` is Kubernetes' own. `kamaji-datastore-manager` comes from the Kamaji
#  app, which the kind cluster doesn't run, so its bindings grant nothing, as on a management
#  cluster without Kamaji.
STATIC_CLUSTER_ROLES = {
    # lines 154-177
    "write-organizations": all_verbs("security.giantswarm.io", "organizations"),
    # lines 233-259
    "write-client-certificates": all_verbs("core.giantswarm.io", "certconfigs"),
    # lines 265-291
    "write-silences": all_verbs("monitoring.giantswarm.io", "silences"),
    # lines 297-323
    "write-policy-exceptions": all_verbs("kyverno.io", "policyexceptions"),
    # lines 329-351: on CAPA management clusters, which the template's cluster examples are
    "write-aws-cluster-role-identity": all_verbs(
        "infrastructure.cluster.x-k8s.io", "awsclusterroleidentities"
    ),
    # lines 357-392
    "cluster-app-chart-lookups": [
        {
            "apiGroups": ["release.giantswarm.io"],
            "resources": ["releases"],
            "verbs": READ,
        },
        {"apiGroups": [""], "resources": ["nodes"], "verbs": READ},
        {
            "apiGroups": ["infrastructure.cluster.x-k8s.io"],
            "resources": ["awsclusterroleidentities"],
            "verbs": READ,
        },
    ],
    # FLUX_APP's `crd-controller`, under the name MC_BASES gives it
    "crd-controller-giantswarm": CRD_CONTROLLER_RULES,
}

# rbac/resource/automation/create.go lines 154-175
PATCH_CHARTS_RULES = [
    {
        "apiGroups": ["application.giantswarm.io"],
        "resources": ["charts"],
        "verbs": ["list", "get", "patch"],
    }
]
WRITE_POLICY_EXCEPTIONS_RULES = all_verbs("kyverno.io", "policyexceptions")
# MC_BASES bases/flux-app-v2/common/resource-rbac.yaml lines 34-46
READ_PODS_AND_LOGS_RULES = [
    {"apiGroups": [""], "resources": ["pods", "pods/log"], "verbs": ["get", "list"]}
]


def cluster_role(name: str, rules: list[dict]) -> dict:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": name, "labels": MANAGED_BY},
        "rules": rules,
    }


def role(name: str, namespace: str, rules: list[dict]) -> dict:
    return {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": name, "namespace": namespace, "labels": MANAGED_BY},
        "rules": rules,
    }


def cluster_roles(read_all: list[dict]) -> list[dict]:
    """Every ClusterRole the `automation` ServiceAccounts are bound to, but `cluster-admin`."""
    return [cluster_role("read-all", read_all)] + [
        cluster_role(name, rules) for name, rules in STATIC_CLUSTER_ROLES.items()
    ]
