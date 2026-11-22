# regions

`bases/environments/regions`

One Component per region. Every cluster lists exactly one, as the `release-aws` chart otherwise creates the cluster in
the management cluster's own region. Each region has the same shape, so this README covers them all.

Nothing applies this directory directly. A cluster lists a region under `components:` in its
`cluster/kustomization.yaml`, and the cluster's Flux `Kustomization` applies the result into the organisation's
namespace, `org-<name>`.

## What's here

- [`eu_central/`](eu_central/): clusters in `eu-central-1`.
- [`eu_central/node_pool/`](eu_central/node_pool/): an extra node pool in the zones of `eu-central-1`, for clusters
  that need more capacity, such as the prod examples.
- [`us_west/`](us_west/): clusters in `us-west-2`.
- [`us_west/node_pool/`](us_west/node_pool/): the same extra node pool in `us-west-2`.

In each region:

- `region_config.yaml`: the values, `global.providerSpecific.region`.
- `kustomization.yaml`: turns them into the `${cluster_name}-region-config` ConfigMap and appends it to the cluster
  `HelmRelease`'s `valuesFrom`.

Each `node_pool/` does the same with `node_pool.yaml` and `${cluster_name}-region-node-pool-config`.

## When you copy it

Copy a region directory for each region you run in, and change the region and the availability zones. Keep the
ConfigMap names: the region's own patch appends them by name, and `WC_NAME_SCHEDULED_UPGRADES`'s
`cluster/cluster-resource-set.yaml` names `${cluster_name}-region-config` in its `valuesFrom`. Keep the patch's
target, the `HelmRelease` `${cluster_name}`, or it misses the cluster. A cluster lists the node pool after its region.

## Read more

- [Regions](/docs/tutorials/intermediate/stages-and-regions.md#regions)
- [Cluster values](/docs/reference/values.md#cluster-values)
