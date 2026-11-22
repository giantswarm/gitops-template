"""Moving a running cluster to scheduled upgrades, as
docs/how-to/scheduled-upgrades-existing-cluster.md does it, has to keep every `valuesFrom` entry
of the cluster's HelmRelease. Checks of cluster_move on the repository's WC_NAME; they need no
cluster, only kubectl."""

from pathlib import Path

from cluster_move import (
    base_values_from,
    copy_cluster,
    move,
    rendered_values_from,
    spec_changes,
    values_from_problems,
)
from kind_config import require_example
from root_build import build

ENTRY_A = {"kind": "ConfigMap", "name": "a", "valuesKey": "values"}
ENTRY_B = {"kind": "ConfigMap", "name": "b", "valuesKey": "values"}


def test_values_from_problems_none() -> None:
    assert values_from_problems([ENTRY_A, ENTRY_B], [ENTRY_A, ENTRY_B]) == []


def test_values_from_problems_missing_entry() -> None:
    assert values_from_problems([ENTRY_A, ENTRY_B], [ENTRY_A]) == [
        "the rendered HelmRelease lacks the valuesFrom entry ConfigMap 'b'"
    ]


def test_values_from_problems_other_order() -> None:
    assert values_from_problems([ENTRY_A, ENTRY_B], [ENTRY_B, ENTRY_A]) == [
        "the rendered HelmRelease merges the valuesFrom entries in another order: "
        "['b', 'a'], not ['a', 'b']"
    ]


def test_move_keeps_the_cluster_values(tmp_path: Path) -> None:
    require_example("capi-wc-name")
    require_example("scheduled-upgrades")
    cluster_dir = copy_cluster(tmp_path)
    before = base_values_from(build(cluster_dir))
    move(cluster_dir)
    after = rendered_values_from(build(cluster_dir))
    assert len(before) == 4, before
    assert values_from_problems(before, after) == []


def test_move_without_retargeting_loses_the_cluster_values(tmp_path: Path) -> None:
    require_example("capi-wc-name")
    require_example("scheduled-upgrades")
    # what the how-to did before: a patch aimed at the HelmRelease matches nothing once the
    #  ResourceSet renders it, and kustomize builds without a word
    cluster_dir = copy_cluster(tmp_path)
    before = base_values_from(build(cluster_dir))
    move(cluster_dir, retarget=False)
    after = rendered_values_from(build(cluster_dir))
    assert values_from_problems(before, after) == [
        "the rendered HelmRelease lacks the valuesFrom entry ConfigMap "
        "'${cluster_name}-cluster-userconfig'"
    ]


def test_spec_changes_none_for_an_implicit_chart_namespace() -> None:
    before = {"chartRef": {"kind": "OCIRepository", "name": "c", "namespace": "ns"}}
    after = {"chartRef": {"kind": "OCIRepository", "name": "c"}}
    assert spec_changes("HelmRelease", before, after, "ns") == []


def test_spec_changes_reports_values() -> None:
    before = {"valuesFrom": [ENTRY_A], "interval": "5m"}
    after = {"valuesFrom": [ENTRY_A, ENTRY_B], "interval": "5m"}
    assert spec_changes("HelmRelease", before, after, "ns") == [
        f"HelmRelease spec.valuesFrom changed from {[ENTRY_A]!r} to "
        f"{[ENTRY_A, ENTRY_B]!r}"
    ]
