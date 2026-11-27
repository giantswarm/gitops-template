# Keep an image current with image automation

Flux image automation keeps the image tag of a workload you write as plain manifests up to date, through pull requests.
image-reflector-controller watches the image's registry, image-automation-controller writes the newest tag your policy
allows into the manifest in Git and pushes the commit to a branch, `flux/image-updates`, and a GitHub workflow opens a
pull request from it. Flux applies the new tag once you merge the pull request. Giant Swarm's flux-app runs both
controllers on every management cluster.

Use it for a workload that isn't a chart, such as a team's own service as a `Deployment`. For an app installed from a
chart, a version range on its `OCIRepository` does the same without a commit, as
[Automatic updates](../tutorials/intermediate/automatic-updates.md) shows.

The [`WC_NAME_IMAGE_AUTOMATION`](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_IMAGE_AUTOMATION/README.md)
example is a finished cluster with a `Deployment` kept current this way. Its `-direct` `Kustomization` applies the
`Deployment` to the workload cluster, as in [Out-of-band resources](../tutorials/advanced/out-of-band.md).

- [What it takes](#what-it-takes)
- [Create the deploy key](#create-the-deploy-key)
- [Add the automation](#add-the-automation)
- [Open pull requests from the branch](#open-pull-requests-from-the-branch)
- [Check it](#check-it)
- [What CI checks](#what-ci-checks)

## What it takes

Five objects in the organisation's namespace on the management cluster, applied by one of the cluster's
`Kustomization`s, and a comment in the manifest:

| Object | What it does |
| --- | --- |
| `ImageRepository` | Lists the image's tags in the registry every `spec.interval`. |
| `ImagePolicy` | Picks the newest of those tags that its semver range allows. |
| `ImageUpdateAutomation` | Clones the repository, writes each policy's tag where a setter comment names the policy, commits, and pushes to `spec.git.push.branch`. |
| `GitRepository` | The repository it clones and pushes to, over SSH. |
| `ExternalSecret` | Writes the deploy key it pushes with from your secret manager. |

The setter comment goes at the end of the line Flux changes, and names the `ImagePolicy` as `<namespace>:<name>`:

```yaml
image: gsoci.azurecr.io/giantswarm/helloworld:0.6.0 # {"$imagepolicy": "org-org-name:image-automation-helloworld"}
```

image-automation-controller reads the file as it is in Git, before Flux substitutes any variable, so the comment names
the namespace and the policy in full, not with `${organization}` or `${cluster_name}`.

The automation needs its own `GitRepository`. The management cluster's reads your fork without write access, and
should stay that way: it's the one every `Kustomization` applies from.

On a management cluster, image-automation-controller needs egress to `github.com` on port 22 to push over SSH. That's
Giant Swarm's to allow, not something the repository configures: ask Giant Swarm before you rely on it.

## Create the deploy key

The automation pushes with a deploy key: an SSH key with write access to your fork and nothing else. Its private half
goes into your secret manager, never into the repository.

1. Generate the key pair outside your clone, so neither half can end up in a commit:

    ```sh
    ssh-keygen -t ed25519 -N "" -C flux-image-updates -f "${TMPDIR:-/tmp}/flux-image-updates"
    ```

1. On GitHub, in your fork's settings under **Deploy keys**, add the contents of
   `${TMPDIR:-/tmp}/flux-image-updates.pub` and tick **Allow write access**.
1. Store the private half, `${TMPDIR:-/tmp}/flux-image-updates`, in your secret manager, for example as
   `gitops/image-updates-deploy-key`, with your secret manager's own tools. Then delete both files.

> [!Caution]
> Don't put the key in the [secret store for testing](./external-secrets.md#a-secret-store-for-testing). Everyone who
> can read the management cluster can read a test store's values, and this key can write to your fork.

## Add the automation

Copy `image-automation/` from the example into your cluster's directory, list it in the `kustomization.yaml` of the
directory your cluster's `Kustomization` applies to the management cluster, and change:

- `git-repository.yaml`: `spec.url`, your fork's SSH URL, such as `ssh://git@github.com/YOUR_ORG/YOUR_REPO`, and
  `spec.ref.branch`, the branch your management cluster's `GitRepository` reads. The automation checks that branch out
  and builds every update on it.
- `externalsecret.yaml`: `secretStoreRef`, your store, and `remoteRef.key`, where you stored the key. `known_hosts` holds
  GitHub's public host keys, from <https://api.github.com/meta>; a fork elsewhere needs its host's.
- `image-repository.yaml`: `spec.image`, your image.
- `image-policy.yaml`: `spec.policy.semver.range`, the versions you take automatically.
- `image-update-automation.yaml`: `spec.update.path`, the directory with your manifests. The automation changes only
  files below it.

Then add the setter comment to your manifest, naming your policy. In the example, the cluster's `Kustomization`
applies the automation with the cluster, and the `-direct` `Kustomization` applies the `Deployment`. The automation
doesn't wait for the cluster: it runs on the management cluster, and needs no apps `Kustomization` or health check.

`spec.git.push.branch` stays `flux/image-updates`, apart from the branch the automation checks out, so every update
comes to you as a pull request. With `push.branch` the same as the checked-out branch, Flux commits straight to it and
applies the update without review.

Flux replaces `flux/image-updates` with every push: each one is the checked-out branch with the newest tags. While an
update waits for its merge, the automation pushes it again at every `spec.interval`, as a new commit, so an hour is a
sensible interval.

## Open pull requests from the branch

[`.github/workflows/image-updates-pull-request.yaml`](/.github/workflows/image-updates-pull-request.yaml) runs on every
push to `flux/image-updates` and opens a pull request from it into your default branch, unless one is open already. It
needs nothing from you in a fork, but one setting: in the repository's settings, under **Actions**, **General**, turn on
**Allow GitHub Actions to create and approve pull requests**. Without it the workflow fails with "GitHub Actions is not
permitted to create or approve pull requests".

If your management cluster's `GitRepository` reads a branch other than the default one, change `BASE` in the workflow
to that branch.

GitHub doesn't run workflows for a pull request that the workflow's own token opens, so your checks don't start when
the pull request appears. They start with the automation's next push, at its next `spec.interval`. To have them sooner,
close the pull request and open it again.

## Check it

Every `ImageRepository`, `ImagePolicy` and `ImageUpdateAutomation` reports `Ready`, and the policy says which tag it
picked:

```sh
flux get images all -n org-${ORG_NAME}
```

After a push, the `ImageUpdateAutomation`'s status names the commit it pushed, which is the head of
`flux/image-updates`:

```sh
kubectl get imageupdateautomation -n org-${ORG_NAME} -o jsonpath='{.items[*].status.lastPushCommit}'
git ls-remote origin refs/heads/flux/image-updates
```

An `ImageUpdateAutomation` that fails to clone or push says so in its `Ready` condition: a key without write access
fails the push, and a key that doesn't match the deploy key fails the clone.

## What CI checks

The kind test runs the example's automation for real, with a deploy key with write access to the template, but pushes
to a branch of each run's own, not to `flux/image-updates`. So it checks that the automation pushes, not that the
workflow opens a pull request: the workflow never runs in CI. See
[Image automation](../reference/ci-checks.md#image-automation) in CI checks.
