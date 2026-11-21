# workload-clusters/HELLO_APP_STAGING_CLUSTER_1

One of four clusters that run the same stack, hello-web, in different stages and regions. This one is the staging
cluster, in `eu-central-1`. The four directories differ only in the Components they list.

The Flux Kustomization `HELLO_APP_STAGING_CLUSTER_1.yaml`, next to this directory in `workload-clusters/`, applies it
into `org-<name>`. The cluster's release comes from its stage, so the Kustomization sets no `release`.

## What's here

- `kustomization.yaml`: lists `cluster/`.
- `cluster/`: the cluster.
  - `kustomization.yaml`: the CAPA base, then the `eu_central` region and the `staging` stage as Components, and a patch
    with the cluster's own values.
  - `cluster_userconfig.yaml`: the cluster's own values, empty here.
  - `patch_cluster_userconfig.yaml`: appends them to the cluster `HelmRelease`'s `valuesFrom`, last.
- `cluster/apps/`: the base apps, installed with the cluster. Its `kustomization.yaml` lists the
  [`hello-web`](/bases/stacks/hello-web/) stack.

## When you copy it

Copy the example whose stage and region you want, rename it and its Kustomization, and set `cluster_name`. To move a
cluster to another stage or region, change its Components, not the bases. Keep the region before the stage, and both
before the patch: the cluster's own values have to come last.

## Read more

- [Stages and regions tutorial](/docs/tutorials/intermediate/stages-and-regions.md#add-clusters-to-the-stages)
- [bases/environments](/bases/environments/)
