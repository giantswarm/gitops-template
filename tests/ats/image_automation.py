"""Runs the image automation example for real, with a push to the repository CI runs against.

The example's `ImageUpdateAutomation` writes the newest helloworld tag its `ImagePolicy` allows
into the Deployment in `out-of-band/` and pushes the commit to `flux/image-updates`, with a deploy
key that its `ExternalSecret` reads from the secret store. The template pins helloworld a tag
behind on purpose, so a push is always due. The kind test makes the push happen, without
pushing to `flux/image-updates`, where the pull request workflow would open a pull request:

1. `image_updates_deploy_key` decrypts the key from fixtures/image-updates with the master key
   CI already has, with a Flux Kustomization, as the shared workflow passes the test no other
   secret.
2. `image_updates_ci_branch` sets `spec.patches` on the cluster's Kustomization, which applies
   the automation. The patch has the automation check out the branch under test and push to a
   branch of this run's own, `flux/image-updates-ci-<time>-<run>`. Flux leaves the field alone,
   as it isn't in Git. Until then the stand-in store doesn't have the key, so the automation
   can't clone, let alone push to `flux/image-updates`. Once Flux has applied the patch, the
   fixture adds the key to the organisation's stand-in store, where the `ExternalSecret` reads
   it, and asks ESO and Flux to act on it now. Nothing else writes the automation's Secret: it
   comes from ESO alone.
3. `check_image_update_pushed` waits for the automation to report a push, and for the branch on
   the remote to be at the commit it pushed.
4. Afterwards the fixture suspends the automation, so it can't push again, and deletes the
   branch, also when a test failed. It also deletes the branches of earlier runs older than
   STALE_AFTER_SEC, which a cancelled run leaves behind.
"""

import base64
import logging
import os
import re
import shlex
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any
from contextlib import contextmanager
from pathlib import Path

import pykube
import pytest
import yaml
from checks.conditions import is_ready, not_ready_reason, obj_key
from conftest import GitOpsTestConfig, apply, run_tool
from eso_kinds import ExternalSecretCR
from external_secrets import organization_store
from flux_reconcile import request_reconcile, suspend, wait_until
from kind_config import REPO_DIR, Ref, kind_test_config
from pykube.objects import NamespacedAPIObject
from pytest_helm_charts.clusters import Cluster
from pytest_helm_charts.flux.git_repository import GitRepositoryCR
from pytest_helm_charts.flux.kustomization import KustomizationCR

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
DEPLOY_KEY_TIMEOUT_SEC = 180

# the test's push branches; the pull request workflow watches `flux/image-updates` only
CI_BRANCH_PREFIX = "flux/image-updates-ci-"
_CI_BRANCH = re.compile(rf"^{re.escape(CI_BRANCH_PREFIX)}(\d+)-")
# A GitHub job runs for 6 hours at most, so a run's branch older than that is one a cancelled
#  run left behind, never one a run still checks.
STALE_AFTER_SEC = 6 * 60 * 60
GIT_URL = "https://git-scm.com/downloads"
# Flux applies the patch on its next reconcile, which the patch's new generation starts
PATCH_TIMEOUT_SEC = 120
# the image reflector scans the registry, then the automation clones, commits and pushes
PUSH_TIMEOUT_SEC = 300

logger = logging.getLogger(__name__)


class ImageUpdateAutomationCR(NamespacedAPIObject):
    version = "image.toolkit.fluxcd.io/v1"
    endpoint = "imageupdateautomations"
    kind = "ImageUpdateAutomation"


class NoKeyError(Exception):
    """The root has no GitRepository or master key to decrypt the fixture with."""

    def __init__(self, management_cluster: str) -> None:
        super().__init__(
            f"The root of '{management_cluster}' needs a GitRepository and a decryption "
            "Secret, so the test can decrypt the image automation example's deploy key"
        )


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


@contextmanager
def ssh_git(identity: str, known_hosts: str) -> Iterator[Callable[..., str]]:
    """A function that runs git with `identity` as its SSH key, trusting `known_hosts`. The
    key lives in a file only the test's user can read, which goes away afterwards."""
    with tempfile.TemporaryDirectory(prefix="image-updates-") as work:
        key = Path(work) / "identity"
        key.touch(mode=0o600)
        key.write_text(identity if identity.endswith("\n") else f"{identity}\n")
        hosts = Path(work) / "known_hosts"
        hosts.write_text(known_hosts)
        ssh = (
            f"ssh -i {shlex.quote(str(key))} -o IdentitiesOnly=yes -o BatchMode=yes "
            f"-o UserKnownHostsFile={shlex.quote(str(hosts))} -o StrictHostKeyChecking=yes"
        )
        repo = Path(work) / "repo"

        def git(*args: str) -> str:
            # run_tool logs the arguments, which name the key's file, never the key
            return run_tool(
                "git", GIT_URL, "-C", str(repo), "-c", f"core.sshCommand={ssh}", *args
            )

        repo.mkdir()
        git("init", "--quiet")
        yield git


def remote_ci_heads(git: Callable[..., str], url: str) -> dict[str, str]:
    """The run branches on the remote, with their commits."""
    return ls_remote_heads(git("ls-remote", url, f"refs/heads/{CI_BRANCH_PREFIX}*"))


def delete_branches(git: Callable[..., str], url: str, branches: list[str]) -> None:
    if branches:
        git("push", url, "--delete", *(f"refs/heads/{b}" for b in branches))
        logger.info(f"Deleted the branches {branches} of {url}")


def _deploy_key_problems(api: pykube.HTTPClient, namespace: str) -> list[str]:
    found = (
        KustomizationCR.objects(api)
        .filter(namespace=namespace)
        .get_or_none(name=DEPLOY_KEY_KUSTOMIZATION)
    )
    if found is None:
        return [f"Kustomization '{namespace}/{DEPLOY_KEY_KUSTOMIZATION}' doesn't exist"]
    if is_ready(found.obj):
        return []
    return [
        f"Kustomization '{namespace}/{DEPLOY_KEY_KUSTOMIZATION}' isn't ready: "
        f"{not_ready_reason(found.obj)}"
    ]


def decrypt_deploy_key(api: pykube.HTTPClient) -> str:
    """The deploy key in the fixture, which Flux decrypts with the root's master key. The
    decrypted Secret goes again with the Kustomization, which prunes it."""
    root = kind_test_config().root(MANAGEMENT_CLUSTER)
    if root.git_repository is None or root.decryption_secret is None:
        raise NoKeyError(MANAGEMENT_CLUSTER)
    namespace = root.decryption_secret[0]
    kustomization = KustomizationCR(
        api, deploy_key_kustomization(root.git_repository, root.decryption_secret)
    )
    apply(kustomization)
    try:
        wait_until(
            lambda: _deploy_key_problems(api, namespace),
            DEPLOY_KEY_TIMEOUT_SEC,
            "the deploy key didn't decrypt",
        )
        secret = (
            pykube.Secret.objects(api)
            .filter(namespace=namespace)
            .get(name=DEPLOY_KEY_NAME)
        )
        return base64.b64decode(secret.obj["data"][DEPLOY_KEY_FIELD]).decode()
    finally:
        kustomization.delete()


def automation(api: pykube.HTTPClient) -> ImageUpdateAutomationCR | None:
    namespace, name = AUTOMATION.split("/")
    return (
        ImageUpdateAutomationCR.objects(api)
        .filter(namespace=namespace)
        .get_or_none(name=name)
    )


def automation_kustomization(api: pykube.HTTPClient) -> KustomizationCR:
    namespace, name = AUTOMATION_KUSTOMIZATION.split("/")
    return KustomizationCR.objects(api).filter(namespace=namespace).get(name=name)


def _get(api: pykube.HTTPClient, kind: type[NamespacedAPIObject], key: str) -> Any:
    namespace, name = key.split("/")
    return kind.objects(api).filter(namespace=namespace).get(name=name)


def hand_over_deploy_key(api: pykube.HTTPClient, identity: str, branch: str) -> None:
    """Once Flux has applied the patch that makes the automation push to `branch`, add the
    key to the stand-in store and have ESO, the GitRepository and the automation use it now,
    rather than at their next retry."""
    wait_until(
        lambda: branch_problems(_automation_obj(api), branch),
        PATCH_TIMEOUT_SEC,
        "Flux didn't apply the image automation's push branch",
    )
    organization_store(api, NAMESPACE, {DEPLOY_KEY_STORE_KEY: identity})
    _get(api, ExternalSecretCR, EXTERNAL_SECRET).patch(
        force_sync_patch(int(time.time()))
    )
    request_reconcile(_get(api, GitRepositoryCR, GIT_REPOSITORY))
    found = automation(api)
    if found is not None:
        request_reconcile(found)


def _automation_obj(api: pykube.HTTPClient) -> dict | None:
    found = automation(api)
    return found.obj if found is not None else None


@pytest.fixture(scope="module")
def image_updates_deploy_key(kube_cluster: Cluster, gitops_root: None) -> str | None:
    """The example's deploy key, or None without the example."""
    reason = kind_test_config().example_skip_reason(EXAMPLE)
    if reason:
        logger.info(f"No image automation deploy key: {reason}")
        return None
    return decrypt_deploy_key(kube_cluster.kube_client)


@pytest.fixture(scope="module")
def image_updates_ci_branch(
    kube_cluster: Cluster,
    gitops_deployment: list[str],
    image_updates_deploy_key: str | None,
    gitops_test_config: GitOpsTestConfig,
) -> Iterator[str | None]:
    """The branch this run's automation pushes to, or None without the example."""
    if image_updates_deploy_key is None:
        yield None
        return
    api = kube_cluster.kube_client
    url = example_git_url()
    now = int(time.time())
    branch = ci_branch(os.environ.get("GITHUB_RUN_ID", "local"), now)
    with ssh_git(image_updates_deploy_key, example_known_hosts()) as git:
        delete_branches(git, url, stale_ci_branches(remote_ci_heads(git, url), now))
        automation_kustomization(api).patch(
            {
                "spec": {
                    "patches": push_patches(
                        gitops_test_config.gitops_repo_branch, branch
                    )
                }
            }
        )
        logger.info(f"The image automation pushes to '{branch}' of {url}")
        try:
            hand_over_deploy_key(api, image_updates_deploy_key, branch)
            yield branch
        finally:
            # suspended, it can't push the branch again once it's deleted
            found = automation(api)
            if found is not None:
                suspend(found)
            if branch in remote_ci_heads(git, url):
                delete_branches(git, url, [branch])


def check_image_update_pushed(
    api: pykube.HTTPClient, identity: str, branch: str
) -> None:
    """Wait for the automation to push to `branch`, and for the branch on the remote to be at
    the commit it pushed."""
    url = example_git_url()
    with ssh_git(identity, example_known_hosts()) as git:

        def problems() -> list[str]:
            obj = _automation_obj(api)
            # the remote is asked only once there's a push to look for
            pushed = obj is not None and _pushed(obj)[0] == branch and _pushed(obj)[1]
            heads = remote_ci_heads(git, url) if pushed else {}
            return push_problems(obj, branch, heads)

        wait_until(problems, PUSH_TIMEOUT_SEC, "the image automation didn't push")
