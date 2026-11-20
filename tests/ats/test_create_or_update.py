"""Checks of how the automation_rbac fixture brings an object that exists already in line; they
need no cluster."""

from typing import cast

import pykube
import pytest
from rbac_reconcile import create_or_update
from rbac_testdata import ref, sa

BINDING = {
    "apiVersion": "rbac.authorization.k8s.io/v1",
    "kind": "RoleBinding",
    "metadata": {"name": "b", "namespace": "a"},
    "roleRef": ref("ClusterRole", "view"),
    "subjects": [sa("a")],
}


class FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> dict:
        return self.body


class FakeAPI:
    """Serves `existing` to a GET and records the method of every request."""

    def __init__(self, existing: dict | None) -> None:
        self.existing = existing
        self.calls: list[str] = []

    def request(self, method: str) -> FakeResponse:
        self.calls.append(method)
        return FakeResponse(200, BINDING)

    def get(self, **kwargs: object) -> FakeResponse:
        self.calls.append("GET")
        if self.existing is None:
            return FakeResponse(404, {})
        return FakeResponse(200, self.existing)

    def post(self, **kwargs: object) -> FakeResponse:
        return self.request("POST")

    def put(self, **kwargs: object) -> FakeResponse:
        return self.request("PUT")

    def delete(self, **kwargs: object) -> FakeResponse:
        return self.request("DELETE")

    def raise_for_status(self, response: FakeResponse) -> None:
        return None


@pytest.mark.parametrize(
    "existing, calls",
    [
        # missing: created
        (None, ["GET", "POST"]),
        # what the API server adds, such as metadata, doesn't count
        ({**BINDING, "metadata": {"uid": "1"}}, ["GET"]),
        # other subjects or rules: replaced, as rbac-operator's CreateOrUpdate does
        ({**BINDING, "subjects": [sa("a"), sa("b")]}, ["GET", "PUT"]),
        # another roleRef, which the API server won't change: deleted and created again, as
        #  `kubectl auth reconcile` does
        (
            {**BINDING, "roleRef": ref("ClusterRole", "cluster-admin")},
            ["GET", "DELETE", "POST"],
        ),
    ],
)
def test_create_or_update(existing: dict | None, calls: list[str]) -> None:
    api = FakeAPI(existing)
    created = create_or_update(
        pykube.RoleBinding(cast(pykube.HTTPClient, api), BINDING)
    )
    assert api.calls == calls
    assert created is (existing is None)
