# ORG_NAME/workload-clusters

The organisation's workload clusters: one directory per cluster, and next to it the Flux Kustomizations that apply it.

The organisation's namespace Kustomization, in `../namespace.yaml`, applies the Kustomizations listed in
`kustomization.yaml` into `org-<name>`, as `../namespace/kustomization.yaml` lists this directory. Those
Kustomizations then apply the cluster directories, as the organisation's `automation` ServiceAccount, decrypting with
the cluster keys in `../namespace/secrets/`.

## What's here

- `kustomization.yaml`: the list of cluster Kustomizations. Add a cluster's files here, or Flux never sees them.
- `<cluster>.yaml`: the cluster's Kustomization. It applies the cluster and its base apps, in `<cluster>/cluster/`.
  Where the cluster has an apps Kustomization, it's Ready only once Cluster API reports the cluster Available.
- `<cluster>-apps.yaml`: the cluster's apps Kustomization. It applies the secondary apps, in `<cluster>/apps/`, once
  the cluster's Kustomization is Ready. Only a cluster with secondary apps has one.
- `<cluster>-direct.yaml`: applies `<cluster>/out-of-band/` straight to the workload cluster, through its kubeconfig.

The examples:

- [`WC_NAME/`](WC_NAME/): a plain cluster with an app whose values are encrypted with an age key.
- [`WC_NAME_OUT_OF_BAND_FLUX_APP/`](WC_NAME_OUT_OF_BAND_FLUX_APP/): Flux installed in the workload cluster.
- [`WC_NAME_OUT_OF_BAND_NO_FLUX_APP/`](WC_NAME_OUT_OF_BAND_NO_FLUX_APP/): out-of-band delivery from the management
  cluster, with ESO and SOPS side by side, and application teams.
- [`WC_NAME_SCHEDULED_UPGRADES/`](WC_NAME_SCHEDULED_UPGRADES/): a cluster whose release upgrades only in a window.
- [`HELLO_APP_DEV_CLUSTER_1/`](HELLO_APP_DEV_CLUSTER_1/),
  [`HELLO_APP_STAGING_CLUSTER_1/`](HELLO_APP_STAGING_CLUSTER_1/),
  [`HELLO_APP_PROD_CLUSTER_EU_CENTRAL/`](HELLO_APP_PROD_CLUSTER_EU_CENTRAL/),
  [`HELLO_APP_PROD_CLUSTER_US_WEST/`](HELLO_APP_PROD_CLUSTER_US_WEST/): the hello-web stack on clusters in several
  stages and regions.

## When you copy it

Copy the example closest to what you want, directory and Kustomizations together, and add the Kustomizations to
`kustomization.yaml`. In the Kustomizations, change the `TODO`s: the names, `cluster_name`, the health check's cluster
name, `release` and the decryption Secret, where the example has them. Keep `spec.path` pointing at the cluster's own
directory, and keep each cluster directory's `kustomization.yaml`: without it, Flux would apply `cluster/` and
`out-of-band/` with the apps.

## Read more

- [3. Create a workload cluster](/docs/tutorials/basic/getting-started.md#3-create-a-workload-cluster)
- [Flux Kustomizations](/docs/reference/repo-structure.md#flux-kustomizations)
- [Delete a workload cluster](/docs/how-to/delete-cluster.md)
