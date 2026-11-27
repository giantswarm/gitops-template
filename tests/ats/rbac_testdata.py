"""Helpers for the tests of automation_bindings: the planned objects by kind, namespace and name,
and the subjects and roleRefs they hold."""

from automation_bindings import automation_rbac_objects

CORE = {"groupVersion": "v1", "resources": [{"name": "pods", "verbs": ["get"]}]}


def sa(namespace: str, name: str = "automation") -> dict:
    return {"kind": "ServiceAccount", "name": name, "namespace": namespace}


def ref(kind: str, name: str) -> dict:
    return {"apiGroup": "rbac.authorization.k8s.io", "kind": kind, "name": name}


def objects(namespaces: list[str], existing: set[str] | None = None) -> dict:
    """The objects automation_bindings plans for `namespaces`, by (kind, namespace, name), on
    a cluster with the namespaces `existing`, by default those and a few of Giant Swarm's.
    """
    if existing is None:
        existing = {"default", "giantswarm", "kube-system", *namespaces}
    planned = automation_rbac_objects(namespaces, existing, [CORE])
    return {
        (o["kind"], o["metadata"].get("namespace", ""), o["metadata"]["name"]): o
        for o in planned
    }
