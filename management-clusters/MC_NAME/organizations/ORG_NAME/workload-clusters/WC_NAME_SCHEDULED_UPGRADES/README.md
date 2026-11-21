# WC_NAME_SCHEDULED_UPGRADES

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES`

A cluster whose Giant Swarm release upgrades only inside a window you choose, such as Tuesday nights, rather than the
moment someone merges. A Flux Operator `ResourceSet` renders the cluster at the release a provider picks, and the
provider only looks for a new release inside its window.

The Flux Kustomization `WC_NAME_SCHEDULED_UPGRADES.yaml`, next to this directory in `workload-clusters/`, applies it
into `org-<name>`. It has no `release` variable: the provider sets it.

## What's here

- `kustomization.yaml`: lists `cluster/`.
- `cluster/`: the cluster.
  - `kustomization.yaml`: the CAPA base and the `eu_central` region, as for any cluster, then the two files below.
  - `release-input-provider.yaml`: the `ResourceSetInputProvider` that picks the highest v36 release, Tuesdays from
    02:00 to 05:00 UTC.
  - `cluster-resource-set.yaml`: the `ResourceSet` that renders the cluster's `OCIRepository` and `HelmRelease` at
    that release. It waits until the provider has a version, so losing the version never deletes the cluster.
  - `patch_delete_base_cluster.yaml`: drops the base's own `OCIRepository` and `HelmRelease`. The base and the region
    still give the cluster its values.

A new provider has no version until its first window opens, so the cluster isn't created until then. To create it at
once, force the provider, as the comment in `release-input-provider.yaml` shows.

## When you copy it

Set `cluster_name` in the Kustomization, and the version range and window in `release-input-provider.yaml`. Keep the
`fluxcd.controlplane.io/prune: disabled` annotations and `giantswarm.io/prevent-deletion` labels in
`cluster-resource-set.yaml`: deleting the `HelmRelease` deletes the cluster. A region's patch doesn't reach into a
`ResourceSet`, so the region's `valuesFrom` entry is written out in it.

## Read more

- [Schedule a cluster's release](/docs/tutorials/advanced/scheduled-upgrades.md#schedule-a-clusters-release)
- [Move a running cluster to ResourceSet upgrades](/docs/how-to/scheduled-upgrades-existing-cluster.md)
