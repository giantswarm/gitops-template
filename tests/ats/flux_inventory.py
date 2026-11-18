"""Reading a Flux Kustomization's inventory, without a cluster."""


def inventory_keys(kustomization: dict) -> set[tuple[str, str, str]]:
    """`(kind, namespace, name)` of every object in the Kustomization's inventory.

    An inventory entry's `id` is `<namespace>_<name>_<group>_<kind>`, with an empty namespace
    for a cluster-scoped object and an empty group for the core API.
    """
    status = kustomization.get("status") or {}
    entries = (status.get("inventory") or {}).get("entries") or []
    keys = set()
    for entry in entries:
        namespace, name, _, kind = entry["id"].split("_")
        keys.add((kind, namespace, name))
    return keys
