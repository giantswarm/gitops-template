"""Checks of the assertion comparison, the HelmRelease checks and the test configuration;
they need no cluster."""

from types import SimpleNamespace
from typing import Any

import pytest
import pytest_helm_charts.utils
import requests
import yaml
from pytest_helm_charts.flux.utils import flux_cr_ready

import test_flux_objects
import conftest
from conftest import installation_values_config_map, parse_ignored_objects
from test_flux_objects import (
    Lookup,
    assert_objects,
    classify,
    depends_on_keys,
    deployment_available,
    helm_releases_to_wait_for,
    is_ready,
    not_ready_reason,
    ready,
    reference_problems,
    releases_without_assertion,
    resource_name,
)


class FakeObject:
    def __init__(self, obj: dict) -> None:
        self.obj = obj


def config_map(data: dict[str, Any]) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "cm", "namespace": "ns"},
        "data": data,
    }


@pytest.mark.parametrize(
    "expected, actual",
    [
        # a block scalar written as `|` in the assertion, `|-` in the repository
        ("a: 1\nb: 2\n", "a: 1\nb: 2"),
        # a stray space at the end of a line
        ("a: 1 \nb: 2\n", "a: 1\nb: 2\n"),
    ],
)
def test_values_ignore_trailing_whitespace(expected: str, actual: str) -> None:
    assert_objects(
        config_map({"values": expected}),
        FakeObject(config_map({"values": actual})),  # type: ignore[arg-type]
        "test",
    )


@pytest.mark.parametrize(
    "expected, actual",
    [
        # single-line values, such as a Secret's base64 `values`
        ({"values": "a: 1"}, {"values": "a: 2"}),
        # a multi-line value
        ({"values": "a: 1\nb: 2\n"}, {"values": "a: 1\nb: 3\n"}),
        # indentation is meaningful in YAML values
        ({"values": "a:\n  b: 1\n"}, {"values": "a:\nb: 1\n"}),
        # another key next to a `values` that differs only in trailing whitespace
        ({"values": "a: 1\n", "other": "x"}, {"values": "a: 1", "other": "y"}),
    ],
)
def test_values_changes_fail(expected: dict, actual: dict) -> None:
    with pytest.raises(pytest.fail.Exception):
        assert_objects(
            config_map(expected),
            FakeObject(config_map(actual)),  # type: ignore[arg-type]
            "test",
        )


def helm_release(value_sources: list[str], extra: dict | None = None) -> dict:
    spec: dict[str, Any] = {
        "valuesFrom": [
            {"kind": "ConfigMap", "name": n, "valuesKey": "values"}
            for n in value_sources
        ]
    }
    spec.update(extra or {})
    return {
        "apiVersion": "helm.toolkit.fluxcd.io/v2",
        "kind": "HelmRelease",
        "metadata": {"name": "hr", "namespace": "ns"},
        "spec": spec,
    }


def test_values_from_order_matters() -> None:
    # Helm merges `valuesFrom` in order, so a reordered list is a different release.
    with pytest.raises(pytest.fail.Exception):
        assert_objects(
            helm_release(["base", "region", "user"]),
            FakeObject(helm_release(["base", "user", "region"])),  # type: ignore[arg-type]
            "test",
        )


def test_other_lists_ignore_order() -> None:
    expected = helm_release(["base"], {"dependsOn": [{"name": "a"}, {"name": "b"}]})
    actual = helm_release(["base"], {"dependsOn": [{"name": "b"}, {"name": "a"}]})
    assert_objects(expected, FakeObject(actual), "test")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("", []),
        ("a/x", ["a/x"]),
        # spaces after the commas, and empty entries
        ("a/x, b/y", ["a/x", "b/y"]),
        (" a/x ,, b/y ,", ["a/x", "b/y"]),
    ],
)
def test_parse_ignored_objects(value: str, expected: list[str]) -> None:
    assert parse_ignored_objects(value) == expected


def test_installation_values_stand_in() -> None:
    # The stand-in has to give the cluster charts the values they need from the management cluster.
    cm = installation_values_config_map(None, "org-org-name")  # type: ignore[arg-type]
    assert cm.obj["metadata"]["name"] == "cluster-app-installation-values"
    values = yaml.safe_load(cm.obj["data"]["values.yaml"])
    assert values["global"]["managementCluster"]
    assert values["global"]["connectivity"]["baseDomain"]


# The HelmRelease checks of the spec in #219, with a lookup in place of a cluster.

CHART_URL = "oci://gsoci.azurecr.io/charts/giantswarm/"


def app(
    name: str,
    chart: str = "hello-world",
    kubeconfig: str | None = "wc-kubeconfig",
    values_from: list[dict] | None = None,
    depends_on: list[str] | None = None,
) -> dict:
    spec: dict[str, Any] = {
        "chartRef": {"kind": "OCIRepository", "name": f"{name}-chart"},
        "valuesFrom": values_from or [],
        "dependsOn": [{"name": d} for d in depends_on or []],
    }
    if kubeconfig:
        spec["kubeConfig"] = {"secretRef": {"name": kubeconfig}}
    return {
        "kind": "HelmRelease",
        "metadata": {"name": name, "namespace": "ns"},
        "spec": spec,
        "_chart": chart,
    }


def lookup_for(hrs: list[dict], *objects: tuple[str, str, dict]) -> Lookup:
    """A lookup that finds `hrs`, their OCIRepositories and `objects` (kind, name, object)."""
    found = {}
    for hr in hrs:
        name = hr["metadata"]["name"]
        found[("HelmRelease", "ns", name)] = hr
        found[("OCIRepository", "ns", f"{name}-chart")] = {
            "spec": {"url": CHART_URL + hr["_chart"]}
        }
    for kind, name, obj in objects:
        found[(kind, "ns", name)] = obj
    return lambda kind, namespace, name: found.get((kind, namespace, name))


KUBECONFIG = ("Secret", "wc-kubeconfig", {"data": {"value": "eA=="}})
CLUSTER_VALUES = ("ConfigMap", "wc-cluster-values", {"data": {"values": "x"}})


@pytest.mark.parametrize(
    "hr, objects, expected",
    [
        (app("a", kubeconfig=None), [], "H1"),
        (app("a", chart="release-aws", kubeconfig=None), [], "H2"),
        (app("a", chart="release-azure", kubeconfig=None), [], "H2"),
        (app("a", chart="release-vsphere", kubeconfig=None), [], "H2"),
        (app("a", chart="release-cloud-director", kubeconfig=None), [], "H2"),
        # the list is fixed: a chart whose name only starts like a cluster chart's, or
        #  another provider's, isn't one
        (app("a", chart="release-aws-extras", kubeconfig=None), [], "H1"),
        (app("a", chart="release-gcp", kubeconfig=None), [], "H1"),
        # the kubeconfig Secret decides, whatever the cluster is called
        (app("a"), [KUBECONFIG], "H3a"),
        (app("a", kubeconfig="other-kubeconfig"), [KUBECONFIG], "H3b"),
        (app("a"), [], "H3b"),
    ],
)
def test_classify(hr: dict, objects: list, expected: str) -> None:
    assert classify(hr, lookup_for([hr], *objects)) == expected


def values_ref(name: str, key: str = "values", optional: bool = False) -> dict:
    ref: dict[str, Any] = {"kind": "ConfigMap", "name": name, "valuesKey": key}
    if optional:
        ref["optional"] = True
    return ref


@pytest.mark.parametrize(
    "hr, hr_class, objects, expected",
    [
        # R2: a required ConfigMap and its key
        (
            app("a", values_from=[values_ref("v")]),
            "H3a",
            [KUBECONFIG],
            ["valuesFrom ConfigMap 'v' doesn't exist"],
        ),
        (
            app("a", values_from=[values_ref("v", key="values.yaml")]),
            "H3a",
            [KUBECONFIG, ("ConfigMap", "v", {"data": {"values": "x"}})],
            ["valuesFrom ConfigMap 'v' has no key 'values.yaml'"],
        ),
        # the content isn't parsed
        (
            app("a", values_from=[values_ref("v")]),
            "H3a",
            [KUBECONFIG, ("ConfigMap", "v", {"data": {"values": "not: [yaml"}})],
            [],
        ),
        # Flux's default key
        (
            app("a", values_from=[{"kind": "Secret", "name": "s"}]),
            "H3a",
            [KUBECONFIG, ("Secret", "s", {"data": {"values.yaml": "eA=="}})],
            [],
        ),
        # an optional reference isn't checked
        (
            app("a", values_from=[values_ref("v", optional=True)]),
            "H3a",
            [KUBECONFIG],
            [],
        ),
        # R3: exempt on H3b, by exact name
        (app("a", values_from=[values_ref("wc-cluster-values")]), "H3b", [], []),
        (
            app("a", values_from=[values_ref("other-cluster-values")]),
            "H3b",
            [],
            ["valuesFrom ConfigMap 'other-cluster-values' doesn't exist"],
        ),
        (
            app(
                "a",
                kubeconfig="wc-admin",
                values_from=[values_ref("wc-cluster-values")],
            ),
            "H3b",
            [],
            [
                "kubeConfig Secret 'wc-admin' doesn't exist",
                "valuesFrom ConfigMap 'wc-cluster-values' doesn't exist",
            ],
        ),
        # ... and on H3b only
        (
            app("a", values_from=[values_ref("wc-cluster-values")]),
            "H3a",
            [KUBECONFIG],
            ["valuesFrom ConfigMap 'wc-cluster-values' doesn't exist"],
        ),
        (
            app("a", values_from=[values_ref("wc-cluster-values")]),
            "H3a",
            [KUBECONFIG, CLUSTER_VALUES],
            [],
        ),
        # R4
        (
            app("a", depends_on=["missing"]),
            "H3a",
            [KUBECONFIG],
            ["dependsOn HelmRelease 'ns/missing' doesn't exist"],
        ),
    ],
)
def test_reference_problems(
    hr: dict, hr_class: str, objects: list, expected: list[str]
) -> None:
    assert reference_problems(hr, hr_class, lookup_for([hr], *objects)) == expected


def test_reference_problems_chart_source() -> None:
    # R1, for a chartRef and for a chart.spec.sourceRef
    hr = app("a")
    assert reference_problems(hr, "H3b", lambda kind, namespace, name: None) == [
        "chart source OCIRepository 'ns/a-chart' doesn't exist"
    ]
    hr["spec"].pop("chartRef")
    hr["spec"]["chart"] = {
        "spec": {"chart": "c", "sourceRef": {"kind": "HelmRepository", "name": "r"}}
    }
    assert reference_problems(hr, "H3b", lambda kind, namespace, name: None) == [
        "chart source HelmRepository 'ns/r' doesn't exist"
    ]


def test_reference_problems_ignored_chart_source() -> None:
    # R1 doesn't look up an ignored source (H4); the other references are still checked
    def lookup(kind: str, namespace: str, name: str) -> dict | None:
        assert kind != "OCIRepository", "looked up the ignored chart source"
        return None

    hr = app("a", kubeconfig=None, values_from=[values_ref("v")])
    assert reference_problems(hr, "H1", lookup, ["ns/a-chart"]) == [
        "valuesFrom ConfigMap 'v' doesn't exist"
    ]


def test_helm_releases_to_wait_for_ignored_chart_source() -> None:
    # H5: an H1 or H3a whose chart source is ignored isn't waited for
    hrs = {
        "ns/h1": app("h1", kubeconfig=None),
        "ns/h3a": app("h3a"),
        "ns/other": app("other"),
    }
    classes = {"ns/h1": "H1", "ns/h3a": "H3a", "ns/other": "H3a"}
    assert helm_releases_to_wait_for(hrs, classes, ["ns/h1-chart", "ns/h3a-chart"]) == {
        "ns/other"
    }


def test_helm_releases_to_wait_for() -> None:
    # "ns/ignored" (H4) isn't listed at all
    hrs = {
        "ns/h1": app("h1", kubeconfig=None),
        "ns/h2": app("h2"),
        "ns/h3a": app("h3a"),
        "ns/h3b": app("h3b"),
        # H5: the dependsOn chain reaches an H2, H3b or H4, directly or not
        "ns/on-h2": app("on-h2", depends_on=["h2"]),
        "ns/on-h3b": app("on-h3b", kubeconfig=None, depends_on=["h3b"]),
        "ns/on-ignored": app("on-ignored", depends_on=["ignored"]),
        "ns/on-on-h3b": app("on-on-h3b", depends_on=["on-h3b"]),
        # not H5
        "ns/on-h3a": app("on-h3a", depends_on=["h3a", "h1"]),
    }
    classes = {
        "ns/h1": "H1",
        "ns/h2": "H2",
        "ns/h3a": "H3a",
        "ns/h3b": "H3b",
        "ns/on-h2": "H3a",
        "ns/on-h3b": "H1",
        "ns/on-ignored": "H3a",
        "ns/on-on-h3b": "H3a",
        "ns/on-h3a": "H3a",
    }
    assert helm_releases_to_wait_for(hrs, classes, ["ns/ignored"]) == {
        "ns/h1",
        "ns/h3a",
        "ns/on-h3a",
    }


@pytest.mark.parametrize(
    "conditions, expected",
    [
        ([], False),
        (
            [
                {"type": "Progressing", "status": "True"},
                {"type": "Available", "status": "True"},
            ],
            True,
        ),
        ([{"type": "Available", "status": "False"}], False),
    ],
)
def test_deployment_available(conditions: list[dict], expected: bool) -> None:
    assert deployment_available({"status": {"conditions": conditions}}) is expected


READY = {"type": "Ready", "status": "True", "message": "Applied revision"}
NOT_READY = {"type": "Ready", "status": "False", "message": "install failed"}
RELEASED = {"type": "Released", "status": "True", "message": "Helm install succeeded"}


@pytest.mark.parametrize(
    "conditions, expected, reason",
    [
        (None, False, "has no conditions"),
        ([], False, "has no conditions"),
        ([READY], True, "Ready is True: Applied revision"),
        ([READY, RELEASED], True, "Ready is True: Applied revision"),
        ([NOT_READY, RELEASED], False, "Ready is False: install failed"),
        # Flux keeps Ready first; a Ready further down isn't read
        ([RELEASED, READY], False, "Released is True: Helm install succeeded"),
    ],
)
def test_is_ready(conditions: list[dict] | None, expected: bool, reason: str) -> None:
    obj: dict = {"status": {"conditions": conditions}} if conditions is not None else {}
    assert is_ready(obj) is expected
    # the same rule as pytest_helm_charts, which the test used before
    assert is_ready(obj) == flux_cr_ready(SimpleNamespace(obj=obj))  # type: ignore[arg-type]
    assert not_ready_reason(obj) == reason


def test_depends_on_keys() -> None:
    hr = app("a")
    hr["spec"]["dependsOn"] = [{"name": "b"}, {"name": "c", "namespace": "other"}]
    assert depends_on_keys(hr) == ["ns/b", "other/c"]


@pytest.mark.parametrize(
    "kind, obj, expected",
    [
        ("OCIRepository", {"status": {"conditions": [READY]}}, True),
        ("OCIRepository", {}, False),
        ("HelmRepository", {"spec": {"type": "default"}}, False),
        # S1: an OCI HelmRepository has no Ready condition, and only has to exist
        ("HelmRepository", {"spec": {"type": "oci"}}, True),
    ],
)
def test_ready(kind: str, obj: dict, expected: bool) -> None:
    assert ready(kind, obj) is expected


GATEWAY_API = {
    "groupVersion": "gateway.networking.k8s.io/v1",
    "resources": [
        {"name": "gateways", "kind": "Gateway"},
        {"name": "gateways/status", "kind": "Gateway"},
        {"name": "gatewayclasses", "kind": "GatewayClass"},
    ],
}


@pytest.mark.parametrize(
    "resource_list, kind, expected",
    [
        (GATEWAY_API, "Gateway", "gateways"),
        (GATEWAY_API, "GatewayClass", "gatewayclasses"),
        # plurals a rule would get wrong
        (
            {"resources": [{"name": "podlogs", "kind": "PodLogs"}]},
            "PodLogs",
            "podlogs",
        ),
        (
            {"resources": [{"name": "endpoints", "kind": "Endpoints"}]},
            "Endpoints",
            "endpoints",
        ),
    ],
)
def test_resource_name(resource_list: dict, kind: str, expected: str) -> None:
    assert resource_name(resource_list, kind) == expected


def test_resource_name_not_served() -> None:
    with pytest.raises(Exception, match="doesn't serve kind 'HTTPRoute'"):
        resource_name(GATEWAY_API, "HTTPRoute")


def test_releases_without_assertion() -> None:
    # W1: an assertion counts for the HelmRelease its `helmRelease` key names
    releases = {"org/a": app("a"), "org/b": app("b"), "org/c": app("c")}
    assertions = [
        {
            "kind": "CustomResourceDefinition",
            "metadata": {"name": "a"},
            "helmRelease": "org/a",
        },
        # Helm's release annotations alone don't make an object the release's main workload
        {
            "kind": "ValidatingAdmissionPolicy",
            "metadata": {
                "name": "b",
                "annotations": {
                    "meta.helm.sh/release-name": "b",
                    "meta.helm.sh/release-namespace": "org",
                },
            },
        },
        {"kind": "Deployment", "metadata": {"name": "c"}, "helmRelease": "org/other"},
    ]
    assert releases_without_assertion(releases, assertions) == ["org/b", "org/c"]


def test_assertion_keys_outside_the_object_are_not_compared() -> None:
    # `helmRelease` is the test's, not a field of the object, so the comparison skips it
    expected = config_map({"values": "a: 1"})
    expected["helmRelease"] = "org/a"
    assert_objects(expected, FakeObject(config_map({"values": "a: 1"})), "test")  # type: ignore[arg-type]


class FakeCluster:
    """Stands in for `list_objects` and `wait_for_ready` of test_flux_objects."""

    def __init__(self, objects: dict[str, list[dict[str, dict]]]) -> None:
        # kind -> what each listing returns, the last one repeated
        self.objects = objects
        self.listed: dict[str, int] = {}
        self.waited: list[set[str]] = []

    def list_objects(self, api: Any, obj_type: Any, ignored: Any) -> dict[str, dict]:
        listings = self.objects.get(obj_type.kind, [{}])
        n = self.listed.get(obj_type.kind, 0)
        self.listed[obj_type.kind] = n + 1
        listing = listings[min(n, len(listings) - 1)]
        return {k: o for k, o in listing.items() if k not in ignored}

    def wait_for_ready(
        self, api: Any, obj_type: Any, keys: Any, timeout_sec: int
    ) -> dict[str, str]:
        self.waited.append(set(keys))
        return {}


def ready_obj() -> dict:
    return {"status": {"conditions": [READY]}}


def test_check_kustomizations_waits_for_ignored_ones_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # K1: the second listing finds the cluster Kustomization the root one created
    cluster = FakeCluster(
        {
            "Kustomization": [
                {"default/root": ready_obj()},
                {"default/root": ready_obj(), "org/ignored": ready_obj()},
            ]
        }
    )
    monkeypatch.setattr(test_flux_objects, "list_objects", cluster.list_objects)
    monkeypatch.setattr(test_flux_objects, "wait_for_ready", cluster.wait_for_ready)
    test_flux_objects.check_kustomizations(None)  # type: ignore[arg-type]
    assert cluster.waited == [{"default/root"}, {"org/ignored"}]


def test_check_kustomizations_fails_without_any(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # E2
    cluster = FakeCluster({})
    monkeypatch.setattr(test_flux_objects, "list_objects", cluster.list_objects)
    with pytest.raises(pytest.fail.Exception, match="no Kustomization"):
        test_flux_objects.check_kustomizations(None)  # type: ignore[arg-type]


def test_check_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    # S1: every source kind; an OCI HelmRepository only has to exist
    cluster = FakeCluster(
        {
            "OCIRepository": [{"ns/oci": ready_obj(), "ns/ignored": {}}],
            "GitRepository": [{"ns/git": ready_obj()}],
            "HelmRepository": [{"ns/helm-oci": {"spec": {"type": "oci"}}}],
            "HelmChart": [{"ns/chart": {}}],
            "Bucket": [{"ns/bucket": ready_obj()}],
        }
    )
    monkeypatch.setattr(test_flux_objects, "list_objects", cluster.list_objects)
    monkeypatch.setattr(test_flux_objects, "SOURCES_READY_TIMEOUT_SEC", 0)
    with pytest.raises(pytest.fail.Exception) as failure:
        test_flux_objects.check_sources(None, ["ns/ignored"])  # type: ignore[arg-type]
    assert str(failure.value).splitlines() == [
        "1 sources aren't ready:",
        "HelmChart 'ns/chart' isn't ready: has no conditions",
    ]
    assert set(cluster.listed) == {
        "OCIRepository",
        "GitRepository",
        "HelmRepository",
        "HelmChart",
        "Bucket",
    }


def test_check_sources_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # E1. A regression guard for the refactored check: passing without sources isn't new
    #  in this PR.
    cluster = FakeCluster({})
    monkeypatch.setattr(test_flux_objects, "list_objects", cluster.list_objects)
    test_flux_objects.check_sources(None, [])  # type: ignore[arg-type]


def patch_helm_releases(
    monkeypatch: pytest.MonkeyPatch, hrs: list[dict], *objects: tuple[str, str, dict]
) -> FakeCluster:
    cluster = FakeCluster(
        {"HelmRelease": [{f"ns/{hr['metadata']['name']}": hr for hr in hrs}]}
    )
    monkeypatch.setattr(test_flux_objects, "list_objects", cluster.list_objects)
    monkeypatch.setattr(test_flux_objects, "wait_for_ready", cluster.wait_for_ready)
    monkeypatch.setattr(
        test_flux_objects, "cluster_lookup", lambda api: lookup_for(hrs, *objects)
    )
    return cluster


def test_check_helm_releases_fails_before_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A missing reference fails at once, without waiting for the releases first
    cluster = patch_helm_releases(
        monkeypatch,
        [app("a", values_from=[values_ref("typo")]), app("b")],
        KUBECONFIG,
    )
    with pytest.raises(pytest.fail.Exception, match="ConfigMap 'typo' doesn't exist"):
        test_flux_objects.check_helm_releases(None, [])  # type: ignore[arg-type]
    assert cluster.waited == []


def test_check_helm_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    # Returns every H3a release, for W1: whichever Secret it reads, and whether or not it
    #  was waited for
    h3a, h3a_other, h3a_h5, h3b, h1 = (
        app("h3a"),
        app("h3a-other", kubeconfig="other-kubeconfig"),
        app("h3a-h5", depends_on=["h3b"]),
        app("h3b", kubeconfig="gone-kubeconfig"),
        app("h1", kubeconfig=None),
    )
    cluster = patch_helm_releases(
        monkeypatch,
        [h3a, h3a_other, h3a_h5, h3b, h1],
        KUBECONFIG,
        ("Secret", "other-kubeconfig", {"data": {"value": "eA=="}}),
    )
    assert test_flux_objects.check_helm_releases(None, []) == {  # type: ignore[arg-type]
        "ns/h3a": h3a,
        "ns/h3a-other": h3a_other,
        "ns/h3a-h5": h3a_h5,
    }
    assert cluster.waited == [{"ns/h3a", "ns/h3a-other", "ns/h1"}]


def test_check_helm_releases_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # E1. A regression guard for the refactored check: passing without HelmReleases isn't
    #  new in this PR.
    cluster = patch_helm_releases(monkeypatch, [])
    assert test_flux_objects.check_helm_releases(None, []) == {}  # type: ignore[arg-type]
    assert cluster.waited == []


def test_load_assertions(tmp_path: Any) -> None:
    # Empty documents, such as a header comment before the first `---`, aren't assertions,
    #  and the result can be read more than once.
    (tmp_path / "a.yaml").write_text(
        "# header\n---\nkind: ConfigMap\nmetadata:\n  name: a\n---\n"
    )
    (tmp_path / "notes.txt").write_text("not an assertion")
    assertions = test_flux_objects.load_assertions(str(tmp_path))
    expected = {
        str(tmp_path / "a.yaml"): [{"kind": "ConfigMap", "metadata": {"name": "a"}}]
    }
    assert assertions == expected
    assert assertions == expected


class FakeAPI:
    """An API server that refuses `refusals` connections, then answers."""

    def __init__(self, refusals: int) -> None:
        self.refusals = refusals
        self.calls = 0

    def get(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls <= self.refusals:
            raise requests.exceptions.ConnectionError("Connection refused")
        return SimpleNamespace(raise_for_status=lambda: None)


def test_wait_for_api(monkeypatch: pytest.MonkeyPatch) -> None:
    # The vCluster's node port can refuse connections for a moment after the install
    monkeypatch.setattr(conftest.time, "sleep", lambda seconds: None)
    api = FakeAPI(refusals=2)
    conftest.wait_for_api(api, 60)  # type: ignore[arg-type]
    assert api.calls == 3


def test_wait_for_api_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conftest.time, "sleep", lambda seconds: None)
    with pytest.raises(TimeoutError, match="didn't answer"):
        conftest.wait_for_api(FakeAPI(refusals=1000), 0)  # type: ignore[arg-type]


class FakeCRD:
    """Stands in for pykube's CustomResourceDefinition; the API server establishes each CRD."""

    created: list[str] = []

    def __init__(self, api: Any, obj: dict) -> None:
        self.obj = obj
        self.name = obj["metadata"]["name"]

    def exists(self) -> bool:
        return False

    def create(self) -> None:
        FakeCRD.created.append(self.name)

    @classmethod
    def objects(cls, api: Any) -> Any:
        established = {
            "status": {"conditions": [{"type": "Established", "status": "True"}]}
        }
        return SimpleNamespace(get=lambda name: SimpleNamespace(obj=established))


def test_install_crds_from_the_fixtures_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # W2: the vCluster's CRDs come from tests/ats/fixtures/crds, not from the network
    monkeypatch.setattr(conftest.pykube, "CustomResourceDefinition", FakeCRD)
    monkeypatch.setattr(FakeCRD, "created", [])
    monkeypatch.setattr(
        conftest.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("downloaded a CRD"),
    )
    conftest.install_crds(None, conftest.WORKLOAD_CLUSTER_CRDS_DIR)  # type: ignore[arg-type]
    assert sorted(FakeCRD.created) == [
        "certificates.cert-manager.io",
        "ciliumnetworkpolicies.cilium.io",
        "clusterpolicies.kyverno.io",
        "dnsendpoints.externaldns.k8s.io",
        "issuers.cert-manager.io",
        "podlogs.monitoring.grafana.com",
        "podmonitors.monitoring.coreos.com",
    ]


def test_remove_workload_cluster_removes_the_values_file_when_the_uninstall_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # A failed `helm uninstall`, such as a `--wait` timeout, mustn't leave the values file behind.
    values_file = tmp_path / "vcluster-values-test.yaml"
    values_file.write_text("{}\n")

    def failing_helm(name: str, url: str, *args: str) -> str:
        raise Exception("`helm uninstall` failed")

    monkeypatch.setattr(conftest, "run_tool", failing_helm)
    with pytest.raises(Exception, match="`helm uninstall` failed"):
        conftest.remove_workload_cluster([], "kubeconfig", str(values_file))
    assert not values_file.exists()


def test_run_tool_not_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conftest.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        conftest.subprocess, "run", lambda *a, **kw: pytest.fail("ran a tool")
    )
    with pytest.raises(Exception, match="`tool` not found"):
        conftest.run_tool("tool", "https://example.com/tool", "arg")


@pytest.mark.parametrize(
    "returncode, stdout, error",
    [
        (0, "output", None),
        (1, "", "`tool sub` failed"),
    ],
)
def test_run_tool(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, error: str | None
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(args: list[str], **kwargs: Any) -> conftest.subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return conftest.subprocess.CompletedProcess(args, returncode, stdout, "err")

    monkeypatch.setattr(conftest.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(conftest.subprocess, "run", run)
    if error:
        with pytest.raises(Exception, match=error):
            conftest.run_tool("tool", "https://example.com/tool", "sub", "--flag")
    else:
        assert (
            conftest.run_tool("tool", "https://example.com/tool", "sub", "--flag")
            == stdout
        )
    # stdout comes back as text, and stderr is captured for the error log
    assert calls == [
        (["/bin/tool", "sub", "--flag"], {"capture_output": True, "text": True})
    ]


class FakeSecret:
    """Stands in for pykube.Secret in wait_for_objects_condition: it shows up after `misses`
    lookups, and records the namespace and name it was looked up by."""

    misses = 0
    lookups: list[tuple[str, str]] = []

    @classmethod
    def objects(cls, api: Any) -> Any:
        return SimpleNamespace(
            filter=lambda namespace: SimpleNamespace(
                get_by_name=lambda name: cls.get(namespace, name)
            )
        )

    @classmethod
    def get(cls, namespace: str, name: str) -> Any:
        cls.lookups.append((namespace, name))
        if len(cls.lookups) <= cls.misses:
            raise conftest.pykube.exceptions.ObjectDoesNotExist()
        return SimpleNamespace(namespace=namespace, name=name)


@pytest.fixture
def fake_secret(monkeypatch: pytest.MonkeyPatch) -> type[FakeSecret]:
    monkeypatch.setattr(conftest.pykube, "Secret", FakeSecret)
    monkeypatch.setattr(FakeSecret, "lookups", [])
    monkeypatch.setattr(pytest_helm_charts.utils.time, "sleep", lambda s: None)
    return FakeSecret


def test_vcluster_kubeconfig_secret(
    monkeypatch: pytest.MonkeyPatch, fake_secret: type[FakeSecret]
) -> None:
    # vCluster writes `vc-<name>` in its namespace some time after the install
    monkeypatch.setattr(fake_secret, "misses", 2)
    secret = conftest.vcluster_kubeconfig_secret(None, 5)  # type: ignore[arg-type]
    expected = ("vcluster-out-of-band-no-flux", "vc-out-of-band-no-flux")
    assert (secret.namespace, secret.name) == expected
    assert fake_secret.lookups == [expected] * 3


def test_vcluster_kubeconfig_secret_names_the_secret_on_timeout(
    monkeypatch: pytest.MonkeyPatch, fake_secret: type[FakeSecret]
) -> None:
    monkeypatch.setattr(fake_secret, "misses", 10)
    with pytest.raises(
        TimeoutError, match="vcluster-out-of-band-no-flux/vc-out-of-band-no-flux"
    ):
        conftest.vcluster_kubeconfig_secret(None, 3)  # type: ignore[arg-type]
    assert len(fake_secret.lookups) == 3
