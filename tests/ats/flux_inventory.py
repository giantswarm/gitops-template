"""Reading a Flux Kustomization's inventory, without a cluster."""


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
