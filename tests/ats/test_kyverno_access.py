"""Checks of what test_flux_objects asks about Kyverno's background controller; they need no
cluster."""

from automation_access import describe, subject_access_review
from kyverno_access import kyverno_access


def test_kyverno_access_in_the_organisation_namespace_only() -> None:
    checks = kyverno_access("org-a")
    assert [(a.name, a.resource, a.namespace, a.allowed) for a in checks] == [
        ("kyverno-background-controller", "externalsecrets", "org-a", True),
        ("kyverno-background-controller", "externalsecrets", "default", False),
    ]


def test_review_of_the_background_controller() -> None:
    spec = subject_access_review(kyverno_access("org-a")[0])["spec"]
    assert (spec["user"], spec["groups"][1]) == (
        "system:serviceaccount:kyverno:kyverno-background-controller",
        "system:serviceaccounts:kyverno",
    )


def test_describe_the_background_controller() -> None:
    assert describe(kyverno_access("org-a")[0]) == (
        "`kyverno/kyverno-background-controller` can't create "
        "externalsecrets.external-secrets.io in `org-a`, which a management cluster allows"
    )
