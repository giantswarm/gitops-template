"""Reading a Flux Kustomization's inventory and whether it built, without a cluster."""

from checks.conditions import obj_key

# the reason of the Ready condition of a Kustomization whose kustomize build failed
BUILD_FAILED = "BuildFailed"


def inventory_keys(kustomization: dict) -> set[tuple[str, str, str]]:
    """`(kind, namespace, name)` of every object in the Kustomization's inventory.

    An inventory entry's `id` is `<namespace>_<name>_<group>_<kind>`, with an empty namespace
    for a cluster-scoped object and an empty group for the core API. A colon in the name, as
    RBAC objects often have, is written as `__`; namespaces, groups and kinds have neither.
    """
    status = kustomization.get("status") or {}
    entries = (status.get("inventory") or {}).get("entries") or []
    keys = set()
    for entry in entries:
        fields = entry["id"].split("_")
        name = "_".join(fields[1:-2]).replace("__", ":")
        keys.add((fields[-1], fields[0], name))
    return keys


def build_failure_problems(
    kustomization: dict, kept: set[tuple[str, str, str]]
) -> list[str]:
    """Why the Kustomization doesn't report that its build failed, or no longer lists the
    objects `kept` in its inventory, if so. A Kustomization whose build fails applies and
    prunes nothing, so its inventory stays as it was."""
    key = obj_key(kustomization)
    conditions = (kustomization.get("status") or {}).get("conditions") or []
    ready: dict = next((c for c in conditions if c.get("type") == "Ready"), {})
    problems = []
    if ready.get("status") != "False" or ready.get("reason") != BUILD_FAILED:
        problems.append(
            f"Kustomization '{key}' doesn't report a failed build: "
            f"Ready is {ready.get('status')} ({ready.get('reason')})"
        )
    missing = sorted(kept - inventory_keys(kustomization))
    if missing:
        problems.append(
            f"Kustomization '{key}' no longer lists {missing} in its inventory"
        )
    return problems


def applied_deployments(
    assertions: list[dict], applied: set[tuple[str, str, str]]
) -> list[dict]:
    """The Deployments among the workload cluster's `assertions` whose `helmRelease` is one of
    the `applied` objects, `(kind, namespace, name)`. Other HelmReleases, such as a
    ResourceSet's, install into the same cluster but aren't the Kustomizations'."""
    releases = {f"{ns}/{name}" for kind, ns, name in applied if kind == "HelmRelease"}
    return [
        a
        for a in assertions
        if a.get("kind") == "Deployment" and a.get("helmRelease") in releases
    ]
