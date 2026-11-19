"""C1: the convention policies in bases/policies/conventions run on the management cluster.

The management cluster's Kustomization applies them from management-clusters/MC_NAME/policies,
next to everything they check, and every Kustomization still has to get ready, so they don't
refuse the examples or Giant Swarm's components. This check makes sure they refuse what breaks
the conventions: the API server has to refuse a dry run of an object that breaks one, and accept
the same object once it's fixed. test_flux_objects.py runs it once the Kustomizations are ready.
"""

import copy
import json

import pykube
from flux_reconcile import wait_until

# what a Flux Kustomization in the `default` namespace labels the objects it applies with
APPLIED_BY_REPOSITORY = {
    "kustomize.toolkit.fluxcd.io/name": "mc-name-gitops",
    "kustomize.toolkit.fluxcd.io/namespace": "default",
}
# Kyverno takes a few seconds to start enforcing a policy Flux has just applied
ENFORCE_TIMEOUT_SEC = 120

KUSTOMIZATION: dict = {
    "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
    "kind": "Kustomization",
    "metadata": {
        "labels": APPLIED_BY_REPOSITORY,
        "name": "conventions-test",
        "namespace": "default",
    },
    "spec": {
        "interval": "10m",
        "path": "./management-clusters/MC_NAME",
        "prune": True,
        "sourceRef": {"kind": "GitRepository", "name": "your-repo"},
    },
}
CLUSTER_HELM_RELEASE: dict = {
    "apiVersion": "helm.toolkit.fluxcd.io/v2",
    "kind": "HelmRelease",
    "metadata": {
        "labels": APPLIED_BY_REPOSITORY,
        "name": "conventions-test",
        "namespace": "org-org-name",
    },
    "spec": {
        "chartRef": {"kind": "OCIRepository", "name": "conventions-test"},
        "interval": "5m",
        "serviceAccountName": "automation",
    },
}
# each object that breaks a convention, what fixes it, and a word the refusal has to name
CASES: list[tuple[dict, dict, str]] = [
    (KUSTOMIZATION, {"spec": {"serviceAccountName": "automation"}}, "automation"),
    (
        CLUSTER_HELM_RELEASE,
        {
            "metadata": {
                "annotations": {"kustomize.toolkit.fluxcd.io/prune": "disabled"},
                "labels": {"giantswarm.io/prevent-deletion": "true"},
            }
        },
        "prevent-deletion",
    ),
]


def merged(obj: dict, fix: dict) -> dict:
    """`obj` with the maps of `fix` merged into it."""
    result = copy.deepcopy(obj)
    for key, value in fix.items():
        if isinstance(value, dict):
            result[key] = merged(result.get(key, {}), value)
        else:
            result[key] = value
    return result


def dry_run_refusal(api: pykube.HTTPClient, obj: dict) -> str:
    """Why the API server refuses to create `obj` on a dry run, or "" if it accepts it."""
    kind = pykube.object_factory(api, obj["apiVersion"], obj["kind"])
    kwargs = kind(api, obj).api_kwargs(
        data=json.dumps(obj), obj_list=True, params={"dryRun": "All"}
    )
    response = api.post(**kwargs)
    if response.ok:
        return ""
    return response.json().get("message", response.text)


def case_problems(api: pykube.HTTPClient, obj: dict, fix: dict, word: str) -> list[str]:
    """Why the policies don't refuse `obj`, naming `word`, or refuse it with `fix`."""
    name = f"{obj['kind']} '{obj['metadata']['namespace']}/{obj['metadata']['name']}'"
    refusal = dry_run_refusal(api, obj)
    if word not in refusal:
        return [f"{name} wasn't refused for '{word}': '{refusal or 'accepted'}'"]
    refusal = dry_run_refusal(api, merged(obj, fix))
    if refusal:
        return [f"{name} was refused once fixed: '{refusal}'"]
    return []


def check_conventions_enforced(api: pykube.HTTPClient) -> None:
    """C1: the policies refuse each case, and accept it once it's fixed."""
    wait_until(
        lambda: [p for case in CASES for p in case_problems(api, *case)],
        ENFORCE_TIMEOUT_SEC,
        "the convention policies don't enforce the conventions",
    )
