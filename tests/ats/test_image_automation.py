"""Checks of how the kind test runs the image automation example, and of the example's files it
reads; they need no cluster."""

from pathlib import Path

import yaml
from fake_store import secret_stores
from image_automation import (
    AUTOMATION,
    AUTOMATION_KUSTOMIZATION,
    CI_BRANCH_PREFIX,
    DEPLOY_KEY_STORE_KEY,
    EXAMPLE,
    EXTERNAL_SECRET_FILE,
    GIT_REPOSITORY_FILE,
    STALE_AFTER_SEC,
    branch_problems,
    ci_branch,
    deploy_key_kustomization,
    example_git_url,
    example_known_hosts,
    ls_remote_heads,
    force_sync_patch,
    push_patches,
    push_problems,
    stale_ci_branches,
)
from kind_config import require_example

SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def test_ci_branch_names_the_time_and_the_run() -> None:
    assert ci_branch("4711", 1764000000) == f"{CI_BRANCH_PREFIX}1764000000-4711"


def test_ci_branch_is_never_the_branch_the_pull_request_workflow_watches() -> None:
    assert ci_branch("4711", 1764000000) != "flux/image-updates"
    assert ci_branch("4711", 1764000000).startswith("flux/image-updates-ci-")


def test_ls_remote_heads() -> None:
    output = (
        f"{SHA}\trefs/heads/flux/image-updates-ci-1-a\n"
        f"{OTHER_SHA}\trefs/heads/flux/image-updates-ci-2-b\n"
    )
    assert ls_remote_heads(output) == {
        "flux/image-updates-ci-1-a": SHA,
        "flux/image-updates-ci-2-b": OTHER_SHA,
    }


def test_ls_remote_heads_of_nothing() -> None:
    assert ls_remote_heads("") == {}


def test_stale_ci_branches_are_the_old_ones_only() -> None:
    now = 1764000000
    old = ci_branch("1", now - STALE_AFTER_SEC - 1)
    recent = ci_branch("2", now - STALE_AFTER_SEC + 60)
    assert stale_ci_branches([old, recent], now) == [old]


def test_stale_ci_branches_leave_other_branches_alone() -> None:
    # a branch that doesn't carry the test's time stamp isn't the test's to delete
    now = 1764000000
    assert (
        stale_ci_branches(
            ["flux/image-updates", f"{CI_BRANCH_PREFIX}soon-1", "main"], now
        )
        == []
    )


def test_push_patches_check_out_the_branch_under_test_and_push_to_the_ci_branch() -> (
    None
):
    patches = push_patches("my-branch", "flux/image-updates-ci-1-a")
    assert len(patches) == 1
    assert patches[0]["target"] == {
        "group": "image.toolkit.fluxcd.io",
        "kind": "ImageUpdateAutomation",
    }
    assert yaml.safe_load(patches[0]["patch"]) == [
        {
            "op": "replace",
            "path": "/spec/git/push/branch",
            "value": "flux/image-updates-ci-1-a",
        },
        {
            "op": "add",
            "path": "/spec/git/checkout",
            "value": {"ref": {"branch": "my-branch"}},
        },
    ]


def automation(branch: str, commit: str | None) -> dict:
    status = {"lastPushCommit": commit} if commit else {}
    return {
        "metadata": {"namespace": "org-a", "name": "b"},
        "spec": {"git": {"push": {"branch": branch}}},
        "status": status,
    }


def test_push_problems_none_when_the_branch_holds_the_pushed_commit() -> None:
    assert push_problems(automation("x", SHA), "x", {"x": SHA}) == []


def test_push_problems_missing_automation() -> None:
    assert push_problems(None, "x", {}) == [
        f"ImageUpdateAutomation '{AUTOMATION}' doesn't exist"
    ]


def test_push_problems_other_branch() -> None:
    # Flux hasn't applied the test's patch: the example would push to flux/image-updates
    assert push_problems(automation("flux/image-updates", SHA), "x", {"x": SHA}) == [
        "ImageUpdateAutomation 'org-a/b' pushes to 'flux/image-updates', not to 'x'"
    ]


def test_push_problems_nothing_pushed_yet() -> None:
    assert push_problems(automation("x", None), "x", {}) == [
        "ImageUpdateAutomation 'org-a/b' hasn't pushed a commit yet"
    ]


def test_push_problems_branch_not_on_the_remote() -> None:
    assert push_problems(automation("x", SHA), "x", {}) == [
        f"branch 'x' isn't on the remote, though 'org-a/b' pushed {SHA} to it"
    ]


def test_push_problems_branch_at_another_commit() -> None:
    assert push_problems(automation("x", SHA), "x", {"x": OTHER_SHA}) == [
        f"branch 'x' is at {OTHER_SHA}, not at {SHA}, the commit 'org-a/b' pushed"
    ]


def test_deploy_key_kustomization_decrypts_the_fixture_with_the_roots_key() -> None:
    k = deploy_key_kustomization(("default", "repo"), ("default", "sops-gpg-master"))
    assert k["metadata"]["namespace"] == "default"
    assert k["spec"]["path"] == "./tests/ats/fixtures/image-updates"
    assert k["spec"]["sourceRef"] == {
        "kind": "GitRepository",
        "name": "repo",
        "namespace": "default",
    }
    assert k["spec"]["decryption"] == {
        "provider": "sops",
        "secretRef": {"name": "sops-gpg-master"},
    }
    # the platform's admission policies refuse a Kustomization without one
    assert k["spec"]["serviceAccountName"] == "automation"
    assert k["spec"]["targetNamespace"] == "default"
    assert k["spec"]["prune"] is True


def test_the_fixture_is_encrypted_and_listed() -> None:
    fixtures = Path(__file__).resolve().parent / "fixtures" / "image-updates"
    kustomization = yaml.safe_load((fixtures / "kustomization.yaml").read_text())
    assert kustomization["resources"] == ["deploy-key.enc.yaml"]
    secret = yaml.safe_load((fixtures / "deploy-key.enc.yaml").read_text())
    assert secret["kind"] == "Secret"
    assert "sops" in secret
    assert secret["stringData"]["identity"].startswith("ENC[")


def test_the_store_serves_the_deploy_key_where_the_example_reads_it() -> None:
    require_example(EXAMPLE)
    stores = secret_stores(["org-a"], {DEPLOY_KEY_STORE_KEY: "key"})
    data = stores[0]["spec"]["provider"]["fake"]["data"]
    assert {"key": DEPLOY_KEY_STORE_KEY, "value": "key"} in data
    external_secret = yaml.safe_load(EXTERNAL_SECRET_FILE.read_text())
    keys = [d["remoteRef"]["key"] for d in external_secret["spec"]["data"]]
    assert keys == [DEPLOY_KEY_STORE_KEY]


def test_the_example_knows_githubs_host_keys() -> None:
    require_example(EXAMPLE)
    lines = example_known_hosts().splitlines()
    assert {line.split()[1] for line in lines} == {
        "ssh-ed25519",
        "ecdsa-sha2-nistp256",
    }
    assert all(line.startswith("github.com ") for line in lines)


def test_the_example_pushes_over_ssh() -> None:
    require_example(EXAMPLE)
    assert example_git_url().startswith("ssh://git@github.com/")
    assert GIT_REPOSITORY_FILE.is_file()


def test_the_example_pushes_to_the_branch_the_workflow_watches() -> None:
    require_example(EXAMPLE)
    automation_file = GIT_REPOSITORY_FILE.parent / "image-update-automation.yaml"
    spec = yaml.safe_load(automation_file.read_text())["spec"]
    assert spec["git"]["push"]["branch"] == "flux/image-updates"
    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[2]
            / ".github/workflows/image-updates-pull-request.yaml"
        ).read_text()
    )
    # PyYAML reads the key `on` as True
    assert workflow[True]["push"]["branches"] == ["flux/image-updates"]


def test_branch_problems_none_once_flux_applied_the_ci_branch() -> None:
    assert branch_problems(automation("x", None), "x") == []


def test_branch_problems_before_flux_applied_the_patch() -> None:
    # the key is handed over only after this, so the example can't push to its own branch
    assert branch_problems(automation("flux/image-updates", None), "x") == [
        "ImageUpdateAutomation 'org-a/b' pushes to 'flux/image-updates', not to 'x'"
    ]


def test_branch_problems_missing_automation() -> None:
    assert branch_problems(None, "x") == [
        f"ImageUpdateAutomation '{AUTOMATION}' doesn't exist"
    ]


def test_force_sync_patch_asks_eso_to_sync_now() -> None:
    assert force_sync_patch(1764000000) == {
        "metadata": {"annotations": {"force-sync": "1764000000"}}
    }


def test_the_clusters_kustomization_applies_the_automation_without_a_health_check() -> (
    None
):
    # kustomize-controller runs 4 reconciles at a time on a management cluster, and a
    #  Kustomization holds one for its whole health check, up to its `timeout`: a fourth cluster
    #  health check of the example organisation leaves none for the apps Kustomizations
    require_example(EXAMPLE)
    example_dir = GIT_REPOSITORY_FILE.parents[1]
    workload_clusters = example_dir.parent
    cluster = yaml.safe_load(
        (workload_clusters / "WC_NAME_IMAGE_AUTOMATION.yaml").read_text()
    )
    assert f"org-org-name/{cluster['metadata']['name']}" == AUTOMATION_KUSTOMIZATION
    assert "healthChecks" not in cluster["spec"]
    assert cluster["spec"]["path"].endswith("/WC_NAME_IMAGE_AUTOMATION")
    root = yaml.safe_load((example_dir / "kustomization.yaml").read_text())
    assert root["resources"] == ["cluster/", "image-automation/"]
    assert not (workload_clusters / "WC_NAME_IMAGE_AUTOMATION-apps.yaml").exists()
