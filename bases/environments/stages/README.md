# stages

`bases/environments/stages`

One Component per stage, each pinning the versions its clusters run: the Giant Swarm release, and the version of
hello-world as an example app. Each stage has the same shape, so this README covers them all.

Nothing applies this directory directly. A cluster lists one stage under `components:` in its
`cluster/kustomization.yaml`, and the cluster's Flux `Kustomization` applies the result into the organisation's
namespace, `org-<name>`.

## What's here

Each directory has one `kustomization.yaml` with JSON patches on the cluster's `OCIRepository`s:

- [`dev/`](dev/): follows the newest dev build of hello-world through a semver range, and pins the release, which
  Renovate bumps in the same pull request as the bases and the `WC_NAME*` clusters.
- [`staging/`](staging/): pins hello-world and the release. Renovate opens its own pull request, on a
  `renovate/staging-*` branch, that nobody merges until dev has run the version.
- [`prod/`](prod/): pins them too, on a `renovate/prod-*` branch, merged after staging has run the version.

A promotion is a merge: dev takes a version first, and the same version reaches staging and then prod as you merge
their pull requests.

## When you copy it

Rename the stages to yours and point the patches at your own apps' `OCIRepository`s, `${cluster_name}-<app>`. Keep the
`# renovate:` comment above each pinned value, or Renovate stops updating it.

## Read more

- [Stages](/docs/tutorials/intermediate/stages-and-regions.md#stages)
- [Promote a change](/docs/tutorials/intermediate/stages-and-regions.md#promote-a-change-from-dev-to-prod)
