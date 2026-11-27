"""Checks of when workload_diagnostics reports the workload cluster's state, and that a failed
test's report shows it; they need no cluster."""

import pytest
from workload_diagnostics import collect, diagnostics_wanted


def test_collect_reports_a_collector_that_fails_and_carries_on() -> None:
    class UnreachableError(Exception):
        def __str__(self) -> str:
            return "connection refused"

    def broken() -> list[str]:
        raise UnreachableError

    assert collect("Pods", broken) == [
        "== Pods",
        "couldn't collect: UnreachableError: connection refused",
    ]
    assert collect("Pods", lambda: ["a"]) == ["== Pods", "a"]


@pytest.mark.parametrize(
    ("when", "failed", "funcargs", "wanted"),
    [
        ("call", True, {"workload_cluster": object()}, True),
        ("call", False, {"workload_cluster": object()}, False),
        ("setup", True, {"workload_cluster": object()}, False),
        ("call", True, {"kube_cluster": object()}, False),
    ],
)
def test_diagnostics_only_for_a_failed_test_of_the_workload_cluster(
    when: str, failed: bool, funcargs: dict, wanted: bool
) -> None:
    assert diagnostics_wanted(when, failed, funcargs) is wanted


def test_a_failed_test_of_the_workload_cluster_reports_its_state(
    pytester: pytest.Pytester,
) -> None:
    # A client that can't reach anything: every collector says so, and the report still shows
    #  the test's own failure.
    pytester.makeconftest("""
        import pytest

        pytest_plugins = ["workload_diagnostics"]


        @pytest.fixture
        def workload_cluster():
            return object()
        """)
    pytester.makepyfile("""
        def test_fails(workload_cluster):
            assert False, "the Deployment isn't available"


        def test_passes(workload_cluster):
            pass
        """)
    result = pytester.runpytest_inprocess("-p", "no:cacheprovider")
    result.assert_outcomes(failed=1, passed=1)
    result.stdout.fnmatch_lines(
        [
            "*the Deployment isn't available*",
            "*- workload cluster diagnostics -*",
            "== workload cluster: Helm history",
            "couldn't collect: *",
            "== workload cluster: Pods",
        ]
    )
    assert result.stdout.str().count("== workload cluster: Helm history") == 1
