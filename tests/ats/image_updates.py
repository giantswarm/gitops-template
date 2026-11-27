"""What the kind test needs to know about the image automation example, and how it judges what
the example's automation did, without a cluster. image_automation runs the example with them.
"""

import re
from collections.abc import Iterable

import yaml
from checks.conditions import obj_key
from kind_config import REPO_DIR, Ref

# the example's binding in kind-test.yaml
EXAMPLE = "image-automation"


EXAMPLE_DIR = (
    REPO_DIR
    / "management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters"
    / "WC_NAME_IMAGE_AUTOMATION"
)


# the management cluster whose root's GitRepository and master key decrypt the fixture
MANAGEMENT_CLUSTER = "MC_NAME"


# the cluster's name, its `cluster_name`; the vCluster stands in for it
CLUSTER = "image-automation"


NAMESPACE = "org-org-name"


# the cluster's Kustomization, which applies the automation
AUTOMATION_KUSTOMIZATION = f"{NAMESPACE}/mc-name-clusters-{CLUSTER}"


AUTOMATION = f"{NAMESPACE}/{CLUSTER}"


AUTOMATION_DIR = EXAMPLE_DIR / "image-automation"


# the example's ExternalSecret and GitRepository, as Flux names them in the cluster
EXTERNAL_SECRET = f"{NAMESPACE}/{CLUSTER}-image-updates-deploy-key"


GIT_REPOSITORY = f"{NAMESPACE}/{CLUSTER}-image-updates"


GIT_REPOSITORY_FILE = AUTOMATION_DIR / "git-repository.yaml"


EXTERNAL_SECRET_FILE = AUTOMATION_DIR / "externalsecret.yaml"


# where the example's ExternalSecret reads the key from
DEPLOY_KEY_STORE_KEY = "gitops/image-updates-deploy-key"


# the fixture, applied by a Kustomization of the test's own
DEPLOY_KEY_PATH = "./tests/ats/fixtures/image-updates"


DEPLOY_KEY_KUSTOMIZATION = "image-updates-deploy-key"


DEPLOY_KEY_NAME = "image-updates-deploy-key"


DEPLOY_KEY_FIELD = "identity"


# the test's push branches; the pull request workflow watches `flux/image-updates` only
CI_BRANCH_PREFIX = "flux/image-updates-ci-"


_CI_BRANCH = re.compile(rf"^{re.escape(CI_BRANCH_PREFIX)}(\d+)-")


# A GitHub job runs for 6 hours at most, so a run's branch older than that is one a cancelled
#  run left behind, never one a run still checks.
STALE_AFTER_SEC = 6 * 60 * 60


def ci_branch(run_id: str, now: int) -> str:
    """The branch a run pushes to: its start, in seconds, and the CI run's ID."""
    return f"{CI_BRANCH_PREFIX}{now}-{run_id}"


def ls_remote_heads(output: str) -> dict[str, str]:
    """The branches in the output of `git ls-remote`, with their commits."""
    heads = {}
    for line in output.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.startswith("refs/heads/"):
            heads[ref.removeprefix("refs/heads/")] = sha
    return heads


def stale_ci_branches(branches: Iterable[str], now: int) -> list[str]:
    """The run branches among `branches` older than STALE_AFTER_SEC."""
    stale = []
    for branch in branches:
        m = _CI_BRANCH.match(branch)
        if m and now - int(m.group(1)) > STALE_AFTER_SEC:
            stale.append(branch)
    return stale


def push_patches(checkout_branch: str, push_branch: str) -> list[dict]:
    """`spec.patches` of the apps Kustomization that have the automation check out
    `checkout_branch` and push to `push_branch`."""
    return [
        {
            "target": {
                "group": "image.toolkit.fluxcd.io",
                "kind": "ImageUpdateAutomation",
            },
            "patch": yaml.safe_dump(
                [
                    {
                        "op": "replace",
                        "path": "/spec/git/push/branch",
                        "value": push_branch,
                    },
                    {
                        "op": "add",
                        "path": "/spec/git/checkout",
                        "value": {"ref": {"branch": checkout_branch}},
                    },
                ]
            ),
        }
    ]


def _pushed(automation: dict) -> tuple[str, str | None]:
    branch = automation["spec"]["git"]["push"]["branch"]
    return branch, (automation.get("status") or {}).get("lastPushCommit")


def branch_problems(automation: dict | None, branch: str) -> list[str]:
    """Why the automation doesn't push to `branch` yet, if it doesn't."""
    if automation is None:
        return [f"ImageUpdateAutomation '{AUTOMATION}' doesn't exist"]
    pushes_to, _ = _pushed(automation)
    if pushes_to != branch:
        return [
            f"ImageUpdateAutomation '{obj_key(automation)}' pushes to '{pushes_to}', "
            f"not to '{branch}'"
        ]
    return []


def force_sync_patch(now: int) -> dict:
    """The patch that has External Secrets Operator sync an ExternalSecret now."""
    return {"metadata": {"annotations": {"force-sync": str(now)}}}


def push_problems(
    automation: dict | None, branch: str, heads: dict[str, str]
) -> list[str]:
    """Why the automation hasn't pushed to `branch` a commit that's on the remote, whose
    branches are `heads`, if it hasn't."""
    problems = branch_problems(automation, branch)
    if automation is None or problems:
        return problems
    key = obj_key(automation)
    _, commit = _pushed(automation)
    if not commit:
        return [f"ImageUpdateAutomation '{key}' hasn't pushed a commit yet"]
    remote = heads.get(branch)
    if remote is None:
        return [
            f"branch '{branch}' isn't on the remote, though '{key}' pushed {commit} to it"
        ]
    if remote != commit:
        return [
            f"branch '{branch}' is at {remote}, not at {commit}, the commit '{key}' pushed"
        ]
    return []


def deploy_key_kustomization(source: Ref, decryption: Ref) -> dict:
    """A Flux Kustomization that applies the fixture into the decryption Secret's namespace,
    decrypted with that Secret. It runs as that namespace's `automation`, as the platform's
    admission policies require."""
    namespace = decryption[0]
    return {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": DEPLOY_KEY_KUSTOMIZATION, "namespace": namespace},
        "spec": {
            "decryption": {"provider": "sops", "secretRef": {"name": decryption[1]}},
            "interval": "1h",
            "path": DEPLOY_KEY_PATH,
            "prune": True,
            "serviceAccountName": "automation",
            "sourceRef": {
                "kind": "GitRepository",
                "name": source[1],
                "namespace": source[0],
            },
            "targetNamespace": namespace,
            "timeout": "2m",
            "wait": True,
        },
    }


def example_known_hosts() -> str:
    """GitHub's host keys, as the example's ExternalSecret writes them for Flux."""
    external_secret = yaml.safe_load(EXTERNAL_SECRET_FILE.read_text())
    return str(external_secret["spec"]["target"]["template"]["data"]["known_hosts"])


def example_git_url() -> str:
    """The repository the example pushes to."""
    return str(yaml.safe_load(GIT_REPOSITORY_FILE.read_text())["spec"]["url"])
