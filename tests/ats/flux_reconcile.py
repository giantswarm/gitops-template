"""Asking Flux to reconcile an object now, and waiting for the result."""

import time
from collections.abc import Callable

from pykube.objects import APIObject
from test_flux_objects import (
    POLL_INTERVAL_SEC,
    fail_on_problems,
    is_ready,
    not_ready_reason,
    obj_key,
)


def request_reconcile(obj: APIObject) -> None:
    """Ask Flux to reconcile `obj` now, as `flux reconcile` does."""
    annotations = {"reconcile.fluxcd.io/requestedAt": str(time.time())}
    obj.patch({"metadata": {"annotations": annotations}})


def suspend(obj: APIObject) -> None:
    """Stop Flux reconciling `obj`, as `flux suspend` does."""
    obj.patch({"spec": {"suspend": True}})


def wait_until(check: Callable[[], list[str]], timeout_sec: int, what: str) -> None:
    """Poll `check` until it returns no problems; fail with the last ones after `timeout_sec`.

    Every wait of the prune checks goes through here.
    """
    deadline = time.monotonic() + timeout_sec
    while True:
        problems = check()
        if not problems:
            return
        if time.monotonic() >= deadline:
            fail_on_problems(problems, f"{what} after {timeout_sec} s")
        time.sleep(POLL_INTERVAL_SEC)


def repo_problems(repo: APIObject) -> list[str]:
    """Why the GitRepository hasn't built an artifact of its current spec yet, if it hasn't."""
    repo.reload()
    observed = (repo.obj.get("status") or {}).get("observedGeneration")
    if observed == repo.obj["metadata"]["generation"] and is_ready(repo.obj):
        return []
    return [f"GitRepository '{obj_key(repo.obj)}': {not_ready_reason(repo.obj)}"]
