# HELLO_APP_PROD_CLUSTER_US_WEST

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_US_WEST`

One of four clusters that run the same stack, hello-web, in different stages and regions. This one is a prod cluster, in
`us-west-2`. The four directories differ in the Components they list, and the two prod clusters in their own
values too.

The Flux `Kustomization` `HELLO_APP_PROD_CLUSTER_US_WEST.yaml`, next to this directory in `workload-clusters/`, applies
it into `org-<name>`. The cluster's release comes from its stage, so the `Kustomization` sets no `release`.

## What's here

- `kustomization.yaml`: lists `cluster/`.
- `cluster/`: the cluster.
  - `kustomization.yaml`: the CAPA base, then the `us_west` region, its extra node pool and the `prod` stage as
    Components, and a patch with the cluster's own values.
  - `cluster_userconfig.yaml`: the cluster's own values, here a bigger `nodepool0`: `m6a.8xlarge`, 10 to 50 nodes.
  - `patch_cluster_userconfig.yaml`: appends them to the cluster `HelmRelease`'s `valuesFrom`, last.
- `cluster/apps/`: the base apps, installed with the cluster. Its `kustomization.yaml` lists the
  [`hello-web`](/bases/stacks/hello-web/) stack.

## When you copy it

Copy the example whose stage and region you want, rename it and its `Kustomization`, and set `cluster_name`. To move a
cluster to another stage or region, change its Components, not the bases. Keep the region before the stage, and both
before the patch: the cluster's own values have to come last.

## Read more

- [Stages and regions tutorial](/docs/tutorials/intermediate/stages-and-regions.md#add-clusters-to-the-stages)
- [bases/environments](/bases/environments/)
