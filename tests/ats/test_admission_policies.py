"""Checks of the platform's admission policies the kind test applies; they need no cluster."""

from admission_policies import (
    POLICIES_DIR,
    SOURCE_COMMIT,
    load_policies,
    ready_problems,
)


def test_the_two_flux_policies_are_loaded() -> None:
    policies = load_policies()
    assert sorted(p["metadata"]["name"] for p in policies) == [
        "flux-multi-tenancy",
        "flux-operator-multi-tenancy",
    ]


def test_the_policies_refuse_rather_than_report() -> None:
    # Audit would let an example the management cluster refuses through
    for policy in load_policies():
        assert policy["kind"] == "ClusterPolicy"
        assert policy["spec"]["validationFailureAction"] == "Enforce"


def test_every_copy_names_the_pinned_commit() -> None:
    files = sorted(POLICIES_DIR.glob("*.yaml"))
    assert len(files) == 2
    for file in files:
        assert SOURCE_COMMIT in file.read_text().splitlines()[0]


def test_ready_problems_none_when_ready() -> None:
    policy = {
        "metadata": {"name": "p"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    assert ready_problems(policy) == []


def test_ready_problems_names_the_reason() -> None:
    policy = {
        "metadata": {"name": "p"},
        "status": {
            "conditions": [
                {
                    "type": "Ready",
                    "status": "False",
                    "reason": "Failed",
                    "message": "webhook not configured",
                }
            ]
        },
    }
    assert ready_problems(policy) == [
        "ClusterPolicy 'p' isn't ready: Failed: webhook not configured"
    ]


def test_ready_problems_without_a_status() -> None:
    assert ready_problems({"metadata": {"name": "p"}}) == [
        "ClusterPolicy 'p' isn't ready: no Ready condition yet"
    ]
