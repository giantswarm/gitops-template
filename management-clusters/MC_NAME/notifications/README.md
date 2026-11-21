# management-clusters/MC_NAME/notifications

Commit statuses on GitHub: each Flux Kustomization in `default` reports, on the commit it applied, whether it worked.
These are the management cluster's Kustomization and each organisation's namespace Kustomization. Each organisation
has its own for the Kustomizations in its namespace, in its `namespace/notifications/`.

The management cluster's Kustomization, in `../MC_NAME.yaml`, applies this directory into the `default` namespace.

## What's here

- `commit-status-provider.yaml`: the `Provider` that posts the statuses to your repository.
- `commit-status-alert.yaml`: the `Alert` that forwards the Kustomizations' events to the `Provider`.
- `commit-status-externalsecret.yaml`: the GitHub token the `Provider` uses, from your secret manager.
- `receiver.yaml` (optional): a `Receiver`, so Flux fetches the repository as soon as GitHub tells it about a push.
- `receiver-externalsecret.yaml` (optional): the secret GitHub signs those calls with.

## When you copy it

Change the `Provider`'s `address` to your repository and the `Receiver`'s `GitRepository` name. Point the
`ExternalSecret`s at your own store, or replace them with SOPS-encrypted Secrets of the same names. Delete the two
`receiver` files if you don't want the webhook.

## Read more

- [Report reconcile status on GitHub commits](/docs/how-to/commit-statuses.md)
