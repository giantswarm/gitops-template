"""Reading a Flux Kustomization's inventory and whether it built, without a cluster."""

from checks.conditions import obj_key

# the reason of the Ready condition of a Kustomization whose kustomize build failed
BUILD_FAILED = "BuildFailed"
# its reason while a Kustomization in its `dependsOn` isn't ready
DEPENDENCY_NOT_READY = "DependencyNotReady"


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


def _held_problems(
    kustomization: dict, reason: str, what: str, kept: set[tuple[str, str, str]]
) -> list[str]:
    key = obj_key(kustomization)
    conditions = (kustomization.get("status") or {}).get("conditions") or []
    ready: dict = next((c for c in conditions if c.get("type") == "Ready"), {})
    problems = []
    if ready.get("status") != "False" or ready.get("reason") != reason:
        problems.append(
            f"Kustomization '{key}' doesn't {what}: "
            f"Ready is {ready.get('status')} ({ready.get('reason')})"
        )
    missing = sorted(kept - inventory_keys(kustomization))
    if missing:
        problems.append(
            f"Kustomization '{key}' no longer lists {missing} in its inventory"
        )
    return problems


def build_failure_problems(
    kustomization: dict, kept: set[tuple[str, str, str]]
) -> list[str]:
    """Why the Kustomization doesn't report that its build failed, or no longer lists the
    objects `kept` in its inventory, if so. A Kustomization whose build fails applies and
    prunes nothing, so its inventory stays as it was."""
    return _held_problems(kustomization, BUILD_FAILED, "report a failed build", kept)


def dependency_wait_problems(
    kustomization: dict, kept: set[tuple[str, str, str]]
) -> list[str]:
    """Why the Kustomization doesn't wait for a Kustomization in its `dependsOn`, or no longer
    lists the objects `kept` in its inventory, if so. A Kustomization that waits applies and
    prunes nothing, so its inventory stays as it was."""
    return _held_problems(
        kustomization, DEPENDENCY_NOT_READY, "wait for a dependency", kept
    )


def left_out_problems(kustomization: dict, left_out: tuple[str, str, str]) -> list[str]:
    """Why the Kustomization hasn't applied its current spec and dropped the object `left_out`
    from its inventory, if it hasn't. A Kustomization drops an object it no longer builds from
    its inventory whether it prunes it or, for one with `kustomize.toolkit.fluxcd.io/prune:
    disabled`, leaves it."""
    key = obj_key(kustomization)
    status = kustomization.get("status") or {}
    if status.get("observedGeneration") != kustomization["metadata"].get("generation"):
        return [f"Kustomization '{key}' hasn't applied its spec yet"]
    conditions = status.get("conditions") or []
    ready: dict = next((c for c in conditions if c.get("type") == "Ready"), {})
    if ready.get("status") != "True":
        return [f"Kustomization '{key}' isn't Ready: {ready.get('reason')}"]
    if left_out in inventory_keys(kustomization):
        return [f"Kustomization '{key}' still lists {left_out}"]
    return []


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
