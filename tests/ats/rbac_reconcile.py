"""How the automation_rbac fixture brings an object that exists already in line with the one it
plans: as rbac-operator's CreateOrUpdate (pkg/rbac) does for rules and subjects, and as
`kubectl auth reconcile` does for a binding's roleRef, which the API server doesn't let it
change.
"""

import json
import logging

import pykube

# what rbac-operator's CreateOrUpdate compares and replaces: the rules of a Role or ClusterRole
#  and the subjects of a binding
CONTENT_KEYS = ("rules", "subjects")

logger = logging.getLogger(__name__)


def needs_update(desired: dict, existing: dict) -> bool:
    return any(desired.get(key) != existing.get(key) for key in CONTENT_KEYS)


def needs_recreate(desired: dict, existing: dict) -> bool:
    return desired.get("roleRef") != existing.get("roleRef")


def create_or_update(kube_obj: pykube.objects.APIObject) -> bool:
    """Create `kube_obj`, or bring the object of its name in line: replace its rules or
    subjects, or delete it and create it again when its roleRef differs. Whether it created
    the object, which didn't exist."""
    api, obj = kube_obj.api, kube_obj.obj
    response = api.get(**kube_obj.api_kwargs())
    if response.status_code == 404:
        kube_obj.create()
        return True
    api.raise_for_status(response)
    existing = response.json()
    if needs_recreate(obj, existing):
        logger.info(f"Recreating {obj['kind']} {kube_obj.name}: its roleRef differs")
        kube_obj.delete()
        kube_obj.create()
    elif needs_update(obj, existing):
        logger.info(f"Replacing {obj['kind']} {kube_obj.name}")
        api.raise_for_status(api.put(**kube_obj.api_kwargs(data=json.dumps(obj))))
    return False
