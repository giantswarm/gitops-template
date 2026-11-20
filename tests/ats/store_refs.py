"""The kinds of the secret stores an External Secrets Operator object reads or writes.

Customers can't create a `ClusterSecretStore` on a management cluster, so every reference in the
examples has to be to a `SecretStore`. test_external_secrets.py checks that.
"""

# ESO's kind for a store reference that names none
DEFAULT_STORE_KIND = "SecretStore"


def ref_kind(ref: dict) -> str:
    return ref.get("kind", DEFAULT_STORE_KIND)


def external_secret_store_kinds(spec: dict) -> list[str]:
    """The stores of an ExternalSecret: `secretStoreRef`, and the `storeRef` of every `data` and
    `dataFrom` entry that reads a store rather than a generator."""
    kinds = []
    if "secretStoreRef" in spec:
        kinds.append(ref_kind(spec["secretStoreRef"]))
    for entry in spec.get("data", []) + spec.get("dataFrom", []):
        store_ref = (entry.get("sourceRef") or {}).get("storeRef")
        if store_ref:
            kinds.append(ref_kind(store_ref))
    return kinds


def store_kinds(doc: dict) -> list[str]:
    """The kinds of the stores `doc` refers to, in order; none for an object that isn't an
    ExternalSecret or a PushSecret."""
    spec = doc.get("spec") or {}
    if doc.get("kind") == "ExternalSecret":
        return external_secret_store_kinds(spec)
    if doc.get("kind") == "PushSecret":
        return [ref_kind(ref) for ref in spec.get("secretStoreRefs", [])]
    return []
