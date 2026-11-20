"""Checks of the rules of `read-all` and of the discovery they're built from; they need no
cluster."""

from typing import cast

import pykube
import pytest
from automation_rbac import discover
from automation_roles import read_all_rules

READ = ["get", "list", "watch"]
POD_LOGS = {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get", "list"]}


def api_list(group_version: str, verbs_by_name: dict[str, list[str]]) -> dict:
    """An APIResourceList of `group_version` with the resources and verbs of `verbs_by_name`."""
    resources = [
        {"name": name, "verbs": verbs} for name, verbs in verbs_by_name.items()
    ]
    return {"groupVersion": group_version, "resources": resources}


def read(group: str, resource: str) -> dict:
    return {"apiGroups": [group], "resources": [resource], "verbs": READ}


CORE = api_list(
    "v1",
    {
        "pods": ["get", "list"],
        "pods/log": ["get"],
        "configmaps": ["get"],
        "secrets": ["get"],
        "bindings": [],
        "namespaces": ["get"],
    },
)
APPS_V1 = api_list("apps/v1", {"deployments": ["get"]})
EXAMPLE_V2 = api_list("example.io/v2", {"widgets": ["get"]})
EXAMPLE_V1 = api_list("example.io/v1", {"widgets": ["get"], "gadgets": ["get"]})
# the preferred version serves `widgets` without verbs, an older one with them
EXAMPLE_V2_VERBLESS = api_list("example.io/v2", {"widgets": []})


@pytest.mark.parametrize(
    "discovery, expected",
    [
        # no ConfigMaps, Secrets, subresources or resources without verbs
        (
            [CORE, APPS_V1],
            [read("", "pods"), read("", "namespaces"), read("apps", "deployments")],
        ),
        # one rule per group and resource, whatever the version
        (
            [EXAMPLE_V2, EXAMPLE_V1],
            [read("example.io", "widgets"), read("example.io", "gadgets")],
        ),
        # the preferred version wins, as in client-go's ServerPreferredResources, even when it
        #  has no verbs and rbac-operator then skips the resource
        ([EXAMPLE_V2_VERBLESS, EXAMPLE_V1], [read("example.io", "gadgets")]),
    ],
)
def test_read_all_rules(discovery: list[dict], expected: list[dict]) -> None:
    assert read_all_rules(discovery) == expected + [POD_LOGS]


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.body


class FakeAPI:
    """Serves discovery bodies by the `version` argument pykube's HTTPClient.get takes."""

    def __init__(self, bodies: dict[str, dict]) -> None:
        self.bodies = bodies

    def get(self, version: str) -> FakeResponse:
        return FakeResponse(self.bodies[version])


def test_discover_lists_the_core_group_then_each_groups_preferred_version_first() -> (
    None
):
    example = {
        "name": "example.io",
        "preferredVersion": {"groupVersion": "example.io/v2"},
        # the API server needn't list the preferred version first
        "versions": [
            {"groupVersion": "example.io/v1"},
            {"groupVersion": "example.io/v2"},
        ],
    }
    bodies = {
        "/apis": {"groups": [example]},
        "v1": CORE,
        "example.io/v1": EXAMPLE_V1,
        "example.io/v2": EXAMPLE_V2,
    }
    api = cast(pykube.HTTPClient, FakeAPI(bodies))
    assert discover(api) == [CORE, EXAMPLE_V2, EXAMPLE_V1]
