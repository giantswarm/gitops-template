# ORG_NAME/multicluster/apps

Apps the organisation installs on several of its workload clusters from one place. Each app is a Flux Operator
`ResourceSet` that renders an `OCIRepository` and a `HelmRelease` for every cluster in `clusters.yaml`. Each app has
the same shape, so this README covers them.

The Flux Kustomization in `../apps.yaml`, in `default`, applies this directory. The `ResourceSet`s and their providers
are in the organisation's namespace, `org-<name>`, and so is what they render.

## What's here

- `clusters.yaml`: the clusters every app here goes to. A patch that `kustomization.yaml` applies to every
  `ResourceSet`. Add a cluster's name to roll the apps out to it; remove it to uninstall them there.
- `kustomization.yaml`: lists each app's files and applies `clusters.yaml` to them.
- [`hello-world-scheduled/`](hello-world-scheduled/): the example app.
  - `input-provider.yaml`: a `ResourceSetInputProvider` that picks the newest hello-world version in a range, only
    inside its upgrade window.
  - `resource-set.yaml`: the `ResourceSet` that installs that version on each cluster. It waits for the provider to
    have a version, so a registry outage never renders nothing and uninstalls the app everywhere.

A new provider has no version until its first window opens. To install at once, force it, as the comment in
`input-provider.yaml` shows.

## When you copy it

Put your clusters' names in `clusters.yaml`. For a new app, copy `hello-world-scheduled/` to a directory named after
it, change the chart, the version range, the window and the names, and list both files in `kustomization.yaml`. Keep
one `ResourceSet` per app: a `ResourceSet` deletes what it rendered for an input that's gone, so apps that shared one
would go together. To give one app its own list of clusters, add a patch after `clusters.yaml` that targets its
`ResourceSet` by name.

## Read more

- [Multicluster apps tutorial](/docs/tutorials/advanced/multicluster-apps.md)
- [Scheduled upgrades tutorial](/docs/tutorials/advanced/scheduled-upgrades.md#schedule-an-apps-upgrades)
