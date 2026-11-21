# ORG_NAME/namespace/notifications

The organisation's commit statuses on GitHub: each Flux Kustomization in the organisation's namespace, such as the
workload clusters' ones, reports on the commit it applied whether it worked. An `Alert` only reaches a `Provider` in its
own namespace, so each organisation has its own.

The organisation's namespace Kustomization, in `../../namespace.yaml`, applies this directory into `org-<name>`. The
management cluster's own `notifications/` covers the Kustomizations in `default`.

## What's here

- `commit-status-provider.yaml`: the `Provider` that posts the statuses to your repository.
- `commit-status-alert.yaml`: the `Alert` that forwards the Kustomizations' events to it.
- `commit-status-externalsecret.yaml`: the GitHub token, from your secret manager.
- `kustomization.yaml`: lists the three.

## When you copy it

Change the `Provider`'s `address` to your repository. Point the `ExternalSecret` at your own store, or replace it with a
SOPS-encrypted Secret of the same name. Delete the directory, and its line in `../kustomization.yaml`, if the
organisation doesn't want commit statuses.

## Read more

- [Report reconcile status on GitHub commits](/docs/how-to/commit-statuses.md)
