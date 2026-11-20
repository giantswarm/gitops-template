"""What the `automation` ServiceAccounts may and may not do, asked of the API server with
SubjectAccessReviews.

It checks the RBAC that automation_rbac sets up as the cluster evaluates it, together with
anything else on the cluster that grants `automation` more, such as objects left over from an
earlier run.
"""

import json
from collections.abc import Callable
from typing import NamedTuple

import pykube
from automation_accounts import DEFAULT_NAMESPACE, PROTECTED_NAMESPACE
from automation_bindings import ORG_NAMESPACE_PREFIX
from rbac_manifests import AUTOMATION


class Access(NamedTuple):
    """Whether the `automation` ServiceAccount of `account` may `verb` a resource in
    `namespace`, or cluster-wide when `namespace` is empty."""

    account: str
    verb: str
    group: str
    resource: str
    namespace: str
    allowed: bool


def expected_access(org: str) -> list[Access]:
    """What a management cluster allows and refuses `default/automation` and the `automation`
    of the organisation namespace `org`."""
    default = DEFAULT_NAMESPACE
    return [
        Access(default, "create", "", "namespaces", "", False),
        Access(default, "get", "", "secrets", "kube-system", False),
        Access(org, "create", "apps", "deployments", default, False),
        Access(default, "create", "apps", "deployments", PROTECTED_NAMESPACE, False),
        Access(org, "patch", "application.giantswarm.io", "charts", "giantswarm", True),
        Access(default, "create", "security.giantswarm.io", "organizations", "", True),
        Access(default, "create", "apps", "deployments", default, True),
        Access(org, "create", "apps", "deployments", org, True),
    ]


def org_namespace(namespaces: list[str]) -> str | None:
    return next((ns for ns in namespaces if ns.startswith(ORG_NAMESPACE_PREFIX)), None)


def subject_access_review(access: Access) -> dict:
    """The SubjectAccessReview of `access`, for the user and groups of the ServiceAccount's
    token."""
    attributes = {
        "verb": access.verb,
        "group": access.group,
        "resource": access.resource,
    }
    if access.namespace:
        attributes["namespace"] = access.namespace
    groups = [
        "system:serviceaccounts",
        f"system:serviceaccounts:{access.account}",
        "system:authenticated",
    ]
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SubjectAccessReview",
        "spec": {
            "user": f"system:serviceaccount:{access.account}:{AUTOMATION}",
            "groups": groups,
            "resourceAttributes": attributes,
        },
    }


def describe(access: Access) -> str:
    can = "can" if not access.allowed else "can't"
    resource = f"{access.resource}.{access.group}" if access.group else access.resource
    where = f"in `{access.namespace}`" if access.namespace else "cluster-wide"
    verdict = "allows" if access.allowed else "refuses"
    return (
        f"`{access.account}/{AUTOMATION}` {can} {access.verb} {resource} {where}, "
        f"which a management cluster {verdict}"
    )


def access_problems(
    review: Callable[[Access], bool], checks: list[Access]
) -> list[str]:
    """What `review` answers differently from a management cluster."""
    return [describe(access) for access in checks if review(access) != access.allowed]


def api_server_review(api: pykube.HTTPClient) -> Callable[[Access], bool]:
    """Ask the API server of `api` whether it allows an Access."""

    def review(access: Access) -> bool:
        response = api.post(
            version="authorization.k8s.io/v1",
            url="subjectaccessreviews",
            data=json.dumps(subject_access_review(access)),
        )
        api.raise_for_status(response)
        return bool(response.json()["status"].get("allowed"))

    return review
