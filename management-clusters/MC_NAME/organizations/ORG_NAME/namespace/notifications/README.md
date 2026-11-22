# notifications

`management-clusters/MC_NAME/organizations/ORG_NAME/namespace/notifications`

The organisation's commit statuses on GitHub: each of the workload clusters' Flux `Kustomization`s in the organisation's
namespace reports, on the commit it applied, whether it worked. An `Alert` only reaches a `Provider` in its own
namespace, so each organisation has its own. The `Alert` lists each `Kustomization` by name, under a `TODO`, rather than
`"*"`: an application team's `Kustomization`, such as `hello-team`, lives in this namespace too, but reads the team's
repository, and GitHub refuses statuses for commits it doesn't know.

The organisation's namespace `Kustomization`, in `../../namespace.yaml`, applies this directory into `org-<name>`. The
management cluster's own `notifications/` covers the `Kustomization`s in `default`.

## What's here

- `commit-status-provider.yaml`: the `Provider` that posts the statuses to your repository.
- `commit-status-alert.yaml`: the `Alert` that forwards the listed `Kustomization`s' events to it.
- `commit-status-externalsecret.yaml`: the GitHub token, from your secret manager.
- `kustomization.yaml`: lists the three.

## When you copy it

Change the `Provider`'s `address` to your repository, and list your workload clusters' `Kustomization`s in the `Alert`'s
`eventSources`, every one in `../../workload-clusters/`. Leave the teams' `Kustomization`s out. Point the
`ExternalSecret` at your own store, or replace it with a SOPS-encrypted Secret of the same name. Delete the directory,
and its line in `../kustomization.yaml`, if the organisation doesn't want commit statuses.

## Read more

- [Report reconcile status on GitHub commits](/docs/how-to/commit-statuses.md)
