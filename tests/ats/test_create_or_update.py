"""Checks of when the automation_rbac fixture replaces an object that exists already; they need
no cluster."""

import pytest
from automation_rbac import needs_update
from rbac_testdata import ref, sa

BINDING = {
    "kind": "RoleBinding",
    "roleRef": ref("ClusterRole", "view"),
    "subjects": [sa("a")],
}
ROLE = {
    "kind": "Role",
    "rules": [{"apiGroups": [""], "resources": ["pods"], "verbs": ["get"]}],
}


@pytest.mark.parametrize(
    "existing, expected",
    [
        # what the API server adds, such as metadata, doesn't count
        ({**BINDING, "metadata": {"uid": "1"}}, False),
        ({**BINDING, "subjects": [sa("a"), sa("b")]}, True),
        ({**BINDING, "roleRef": ref("ClusterRole", "cluster-admin")}, True),
        (ROLE, True),
    ],
)
def test_needs_update_compares_rules_subjects_and_role_ref(
    existing: dict, expected: bool
) -> None:
    # as rbac-operator's CreateOrUpdate does, rather than leave a stale object as it is
    assert needs_update(BINDING, existing) is expected
