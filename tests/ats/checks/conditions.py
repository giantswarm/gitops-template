"""What the status of a Flux object says."""


def obj_key(obj: dict) -> str:
    return f"{obj['metadata'].get('namespace', '')}/{obj['metadata']['name']}"


def condition_true(obj: dict, condition_type: str) -> bool:
    conditions = (obj.get("status") or {}).get("conditions") or []
    return any(
        c.get("type") == condition_type and c.get("status") == "True"
        for c in conditions
    )


def is_ready(obj: dict) -> bool:
    """Whether a Flux object is Ready.

    pytest_helm_charts' `flux_cr_ready` rule, for an object rather than an API object, and
    without its warning on every poll: Flux keeps Ready as the first condition, so that one
    has to be Ready and True.
    """
    conditions = (obj.get("status") or {}).get("conditions") or []
    return (
        bool(conditions)
        and conditions[0].get("type") == "Ready"
        and conditions[0].get("status") == "True"
    )


def describe(condition: dict) -> str:
    return (
        f"{condition.get('type')} is {condition.get('status')}: "
        f"{condition.get('message', '')}"
    )


def later_ready(conditions: list[dict]) -> list[dict]:
    """The Ready conditions after the first condition."""
    return [c for c in conditions[1:] if c.get("type") == "Ready"]


def not_ready_reason(obj: dict) -> str:
    """Why `is_ready` says no: the first condition, which is the one it reads, and the Ready
    condition when that isn't the first, as it holds the error while Flux retries."""
    conditions = (obj.get("status") or {}).get("conditions") or []
    if not conditions:
        return "has no conditions"
    return "; ".join(describe(c) for c in conditions[:1] + later_ready(conditions))


def ready(kind: str, obj: dict) -> bool:
    """`is_ready`, except for an OCI HelmRepository: Flux doesn't reconcile one, so it has no
    Ready condition and only has to exist (S1)."""
    oci_helm_repository = (
        kind == "HelmRepository" and (obj.get("spec") or {}).get("type") == "oci"
    )
    return oci_helm_repository or is_ready(obj)
