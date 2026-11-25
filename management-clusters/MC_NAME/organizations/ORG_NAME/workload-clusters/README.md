# workload-clusters

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters`

The organisation's workload clusters: one directory per cluster, and next to it the Flux `Kustomization`s that apply it.

The organisation's namespace `Kustomization`, in `../namespace.yaml`, applies the `Kustomization`s listed in
`kustomization.yaml` into `org-<name>`, as `../namespace/kustomization.yaml` lists this directory. Those
`Kustomization`s then apply the cluster directories, as the organisation's `automation` ServiceAccount, decrypting with
the cluster keys in `../namespace/secrets/`.

## What's here

- `kustomization.yaml`: the list of cluster `Kustomization`s. Add a cluster's files here, or Flux never sees them.
- `<cluster>.yaml`: the cluster's `Kustomization`. It applies the cluster and its base apps, in `<cluster>/cluster/`.
  Where the cluster has an apps `Kustomization`, it's `Ready` only once Cluster API reports the cluster's control plane
  available and reachable.
- `<cluster>-apps.yaml`: the cluster's apps `Kustomization`. It applies the secondary apps, in `<cluster>/apps/`, once
  the cluster's `Kustomization` is `Ready`. Only a cluster with secondary apps has one.
- `<cluster>-direct.yaml`: applies `<cluster>/out-of-band/` straight to the workload cluster, through its kubeconfig.
  Only a cluster whose `out-of-band/` the management cluster pushes has one.

A cluster's `out-of-band/` holds what goes straight into the workload cluster rather than onto the management cluster,
and it gets there one of two ways. The management cluster pushes it, with a Flux `Kustomization` whose `kubeConfig`
reaches the workload cluster, as in `WC_NAME_OUT_OF_BAND_NO_FLUX_APP`. Or the workload cluster's own Flux pulls it from
the repository, as in `WC_NAME_OUT_OF_BAND_FLUX_APP`. `-direct` is only the name this template gives the pushing
`Kustomization`, not a kind of Flux object.

The examples:

- [`WC_NAME/`](WC_NAME/): a plain cluster with an app whose values are encrypted with an age key.
- [`WC_NAME_OUT_OF_BAND_FLUX_APP/`](WC_NAME_OUT_OF_BAND_FLUX_APP/): out-of-band delivery pulled by Flux in the
  workload cluster.
- [`WC_NAME_OUT_OF_BAND_NO_FLUX_APP/`](WC_NAME_OUT_OF_BAND_NO_FLUX_APP/): out-of-band delivery pushed by the
  management cluster, with External Secrets Operator and SOPS side by side, and application teams.
- [`WC_NAME_SCHEDULED_UPGRADES/`](WC_NAME_SCHEDULED_UPGRADES/): a cluster whose release upgrades only in a window.
- [`WC_NAME_IMAGE_AUTOMATION/`](WC_NAME_IMAGE_AUTOMATION/): a plain `Deployment` without Helm, pushed by the management
  cluster, whose image Flux image automation keeps current through pull requests.
- [`HELLO_APP_DEV_CLUSTER_1/`](HELLO_APP_DEV_CLUSTER_1/),
  [`HELLO_APP_STAGING_CLUSTER_1/`](HELLO_APP_STAGING_CLUSTER_1/),
  [`HELLO_APP_PROD_CLUSTER_EU_CENTRAL/`](HELLO_APP_PROD_CLUSTER_EU_CENTRAL/),
  [`HELLO_APP_PROD_CLUSTER_US_WEST/`](HELLO_APP_PROD_CLUSTER_US_WEST/): the hello-web stack on clusters in several
  stages and regions.

## When you copy it

Copy the example closest to what you want, directory and `Kustomization`s together, and add the `Kustomization`s to
`kustomization.yaml`, and by name to the `eventSources` of the organisation's commit status `Alert`, in
`../namespace/notifications/commit-status-alert.yaml`. In the `Kustomization`s, change the `TODO`s: the names,
`cluster_name`, the health check's cluster name, `release` and the decryption Secret, where the example has them. Keep
`spec.path` pointing at the cluster's own directory, and keep each cluster directory's `kustomization.yaml`: without it,
Flux would apply `cluster/` and `out-of-band/` with the apps.

## Read more

- [3. Create a workload cluster](/docs/tutorials/basic/getting-started.md#3-create-a-workload-cluster)
- [Flux `Kustomization`s](/docs/reference/repo-structure.md#flux-kustomizations)
- [Delete a workload cluster](/docs/how-to/delete-cluster.md)
