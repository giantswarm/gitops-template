# image-automation

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_IMAGE_AUTOMATION/apps/image-automation`

The Flux image automation that keeps the `Deployment` in `../../out-of-band/helloworld/` current. All of it runs on the
management cluster, in `org-<name>`, applied by the cluster's apps `Kustomization`.

## What's here

- `image-repository.yaml`: an `ImageRepository`. image-reflector-controller lists the image's tags in the registry
  every hour.
- `image-policy.yaml`: an `ImagePolicy`, which picks the newest of those tags in its semver range.
- `image-update-automation.yaml`: an `ImageUpdateAutomation`. image-automation-controller clones the repository, writes
  the policy's tag into every file below `update.path` with a setter comment naming the policy, commits, and pushes to
  `flux/image-updates`. It takes only the policies with the cluster's label.
- `git-repository.yaml`: the `GitRepository` it clones and pushes to, over SSH. It's not the management cluster's
  `GitRepository`, which reads your fork without write access.
- `externalsecret.yaml`: the `ExternalSecret` that writes the deploy key, `identity`, from your secret manager, and
  GitHub's host keys, `known_hosts`, into the Secret the `GitRepository` reads.

The setter comment and the policy have to agree: the comment in `deployment.yaml` names the policy as
`<namespace>:<name>`, with the names in full, as Flux reads the file in Git before it substitutes any variable.

## When you copy it

Follow [`WC_NAME_IMAGE_AUTOMATION/README.md`](../../README.md#when-you-copy-it). To keep more than one image current,
add an `ImageRepository` and an `ImagePolicy` for each, with a setter comment for each: the one
`ImageUpdateAutomation` handles them all.

## Read more

- [Image automation](/docs/how-to/image-automation.md)
- [Flux's image automation guide](https://fluxcd.io/flux/guides/image-update/)
