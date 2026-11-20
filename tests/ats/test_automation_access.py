"""Checks of the SubjectAccessReviews test_flux_objects asks about the `automation`
ServiceAccounts; they need no cluster."""

import pytest
from automation_access import (
    Access,
    access_problems,
    expected_access,
    org_namespace,
    subject_access_review,
)

CREATE_DEPLOYMENTS = Access("org-a", "create", "apps", "deployments", "org-a", True)
CREATE_NAMESPACES = Access("default", "create", "", "namespaces", "", False)


def test_review_of_a_namespaced_resource() -> None:
    assert subject_access_review(CREATE_DEPLOYMENTS) == {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SubjectAccessReview",
        "spec": {
            "user": "system:serviceaccount:org-a:automation",
            "groups": [
                "system:serviceaccounts",
                "system:serviceaccounts:org-a",
                "system:authenticated",
            ],
            "resourceAttributes": {
                "verb": "create",
                "group": "apps",
                "resource": "deployments",
                "namespace": "org-a",
            },
        },
    }


def test_review_of_a_cluster_scoped_resource_has_no_namespace() -> None:
    attributes = subject_access_review(CREATE_NAMESPACES)["spec"]["resourceAttributes"]
    assert "namespace" not in attributes


def test_access_problems_name_each_answer_that_differs() -> None:
    problems = access_problems(
        lambda access: True, [CREATE_DEPLOYMENTS, CREATE_NAMESPACES]
    )
    assert problems == [
        "`default/automation` can create namespaces cluster-wide, which a management cluster refuses"
    ]


def test_access_problems_of_a_refused_access() -> None:
    problems = access_problems(lambda access: False, [CREATE_DEPLOYMENTS])
    assert problems == [
        "`org-a/automation` can't create deployments.apps in `org-a`, which a management cluster allows"
    ]


def test_expected_access_checks_both_accounts_both_ways() -> None:
    checks = expected_access("org-a")
    assert {(a.account, a.allowed) for a in checks} == {
        ("default", True),
        ("default", False),
        ("org-a", True),
        ("org-a", False),
    }


@pytest.mark.parametrize(
    "namespaces, expected",
    [(["default", "org-a", "org-b"], "org-a"), (["default"], None)],
)
def test_org_namespace(namespaces: list[str], expected: str | None) -> None:
    assert org_namespace(namespaces) == expected
