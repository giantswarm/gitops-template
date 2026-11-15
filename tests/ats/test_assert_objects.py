"""Checks of the assertion comparison and of the HelmRelease reference checks; they need no cluster."""

import base64
from typing import Any

import pytest
from pytest_helm_charts.flux.helm_release import HelmReleaseCR

from test_flux_objects import (
    OCIRepositoryCR,
    assert_objects,
    chart_problems,
    helm_release_problems,
    inventory_objects,
    parse_inventory_id,
    values_from_problems,
    workload_cluster_names,
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


class FakeIndex:
    """Serves objects by `(kind, namespace, name)`, like ClusterIndex does from the cluster."""

    def __init__(self, *objects: tuple[str, dict]) -> None:
        self.objects = {
            (kind, o["metadata"]["namespace"], o["metadata"]["name"]): o
            for kind, o in objects
        }

    def get(self, kind: str, namespace: str, name: str) -> dict | None:
        return self.objects.get((kind, namespace, name))


def obj(name: str, namespace: str = "ns", **fields: Any) -> dict:
    return {"metadata": {"name": name, "namespace": namespace}, **fields}


def ready(name: str, status: str = "True", namespace: str = "ns") -> dict:
    return obj(
        name, namespace, status={"conditions": [{"type": "Ready", "status": status}]}
    )


def release(spec: dict, labels: dict | None = None) -> dict:
    return {
        "metadata": {"name": "app", "namespace": "ns", "labels": labels or {}},
        "spec": {"chartRef": {"kind": "OCIRepository", "name": "app"}, **spec},
    }


def chart_from(kind: str, name: str) -> dict:
    return {
        "chart": {"spec": {"chart": "x", "sourceRef": {"kind": kind, "name": name}}}
    }


def b64(text: bytes) -> str:
    return base64.b64encode(text).decode()


def test_values_from_target_path_holds_a_single_value() -> None:
    hr = release(
        {
            "valuesFrom": [
                {
                    "kind": "Secret",
                    "name": "password",
                    "valuesKey": "password",
                    "targetPath": "auth.password",
                }
            ]
        }
    )
    index = FakeIndex(("Secret", obj("password", data={"password": b64(b"s3cr3t")})))
    assert values_from_problems(hr, index) == []  # type: ignore[arg-type]


def test_values_from_without_target_path_needs_a_mapping() -> None:
    hr = release({"valuesFrom": [{"kind": "ConfigMap", "name": "v", "valuesKey": "v"}]})
    index = FakeIndex(("ConfigMap", obj("v", data={"v": "just a string"})))
    assert values_from_problems(hr, index) == [  # type: ignore[arg-type]
        "ConfigMap 'v' key 'v' isn't a YAML mapping"
    ]


@pytest.mark.parametrize(
    "value",
    [
        b64(b"\xff\xfe binary"),  # not UTF-8
        "not base64!",
    ],
)
def test_values_from_undecodable_secret_is_a_problem(value: str) -> None:
    hr = release(
        {
            "valuesFrom": [
                {"kind": "Secret", "name": "bad", "valuesKey": "values"},
                {"kind": "ConfigMap", "name": "missing", "valuesKey": "values"},
            ]
        }
    )
    index = FakeIndex(("Secret", obj("bad", data={"values": value})))
    problems = values_from_problems(hr, index)  # type: ignore[arg-type]
    # the problem is reported, and the references after it are still checked
    assert len(problems) == 2
    assert problems[0].startswith("Secret 'bad' key 'values' isn't base64-encoded text")
    assert problems[1] == "ConfigMap 'missing' doesn't exist"


@pytest.mark.parametrize(
    "secret, labels, expected",
    [
        ("c1-kubeconfig", {}, {"c1"}),
        # not Cluster API's Secret name: the labels give the cluster
        ("c1-kubeconfig-admin", {"giantswarm.io/cluster": "c1"}, {"c1"}),
        ("admin", {"cluster.x-k8s.io/cluster-name": "c1"}, {"c1"}),
        ("c1-kubeconfig-admin", {}, set()),
    ],
)
def test_workload_cluster_names(secret: str, labels: dict, expected: set) -> None:
    hr = release({"kubeConfig": {"secretRef": {"name": secret}}}, labels)
    assert workload_cluster_names(hr) == expected


def test_no_workload_cluster_without_kubeconfig() -> None:
    assert workload_cluster_names(release({}, {"giantswarm.io/cluster": "c1"})) == set()


def test_cluster_values_skipped_for_custom_kubeconfig_secret() -> None:
    hr = release(
        {
            "kubeConfig": {"secretRef": {"name": "c1-kubeconfig-admin"}},
            "valuesFrom": [
                {
                    "kind": "ConfigMap",
                    "name": "c1-cluster-values",
                    "valuesKey": "values",
                }
            ],
        },
        {"giantswarm.io/cluster": "c1"},
    )
    assert values_from_problems(hr, FakeIndex()) == []  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "spec, objects, expected",
    [
        # chartRef to an OCIRepository
        ({}, [("OCIRepository", ready("app"))], []),
        (
            {},
            [("OCIRepository", ready("app", "False"))],
            ["OCIRepository 'ns/app' isn't ready"],
        ),
        ({}, [], ["OCIRepository 'ns/app' doesn't exist"]),
        # chartRef to a HelmChart in another namespace
        (
            {"chartRef": {"kind": "HelmChart", "name": "c", "namespace": "flux"}},
            [("HelmChart", ready("c", namespace="flux"))],
            [],
        ),
        # chart with a HelmRepository, GitRepository or Bucket source
        (
            {"chartRef": None, **chart_from("HelmRepository", "repo")},
            [("HelmRepository", ready("repo"))],
            [],
        ),
        (
            # an OCI HelmRepository has no status, it only has to exist
            {"chartRef": None, **chart_from("HelmRepository", "oci")},
            [("HelmRepository", obj("oci", spec={"type": "oci"}))],
            [],
        ),
        (
            {"chartRef": None, **chart_from("GitRepository", "git")},
            [],
            ["GitRepository 'ns/git' doesn't exist"],
        ),
        (
            {"chartRef": None, **chart_from("Bucket", "b")},
            [("Bucket", ready("b", "False"))],
            ["Bucket 'ns/b' isn't ready"],
        ),
    ],
)
def test_chart_problems(spec: dict, objects: list, expected: list) -> None:
    assert chart_problems(release(spec), FakeIndex(*objects)) == expected  # type: ignore[arg-type]


def test_missing_chart_source_is_reported() -> None:
    # Without its OCIRepository a cluster chart can't be told apart from an app, but the
    # missing source is a problem, so the HelmRelease is reported instead of waited for.
    assert helm_release_problems(release({}), FakeIndex()) == [  # type: ignore[arg-type]
        "OCIRepository 'ns/app' doesn't exist"
    ]


@pytest.mark.parametrize(
    "entry, expected",
    [
        (
            "org-a_c1-app_helm.toolkit.fluxcd.io_HelmRelease",
            ("helm.toolkit.fluxcd.io", "HelmRelease", "org-a", "c1-app"),
        ),
        ("org-a_c1-values__ConfigMap", ("", "ConfigMap", "org-a", "c1-values")),
        ("_org-a__Namespace", ("", "Namespace", "", "org-a")),
        ("broken", None),
    ],
)
def test_parse_inventory_id(entry: str, expected: tuple | None) -> None:
    assert parse_inventory_id(entry) == expected


def kustomization(name: str, ids: list[str], **spec: Any) -> dict:
    return {
        "metadata": {"name": name, "namespace": "default"},
        "spec": spec,
        "status": {"inventory": {"entries": [{"id": i, "v": "v2"} for i in ids]}},
    }


def test_inventory_objects() -> None:
    hr_id = "org-a_{}_helm.toolkit.fluxcd.io_HelmRelease"
    kustomizations = [
        kustomization("root", ["_org-a__Namespace", hr_id.format("c1-app")]),
        kustomization("ignored", [hr_id.format("c2-app")]),
        # applies to a workload cluster, so its objects aren't in this one
        kustomization(
            "remote",
            [hr_id.format("c3-app")],
            kubeConfig={"secretRef": {"name": "c3-kubeconfig"}},
        ),
        # not reconciled yet
        {"metadata": {"name": "new", "namespace": "default"}, "spec": {}},
    ]
    assert inventory_objects(kustomizations, HelmReleaseCR, ["default/ignored"]) == {
        "org-a/c1-app"
    }
    assert inventory_objects(kustomizations, OCIRepositoryCR, []) == set()
