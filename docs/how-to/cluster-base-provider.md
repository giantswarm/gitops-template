# Create a cluster base for another provider

The template ships one provider's base, [bases/clusters/capa](/bases/clusters/capa/), for AWS. For clusters on another
provider, such as Azure with CAPZ, create a base for it next to it. `kubectl gs gitops add base` writes most of it; this
page covers the rest. To build a base with your own defaults on top of a provider's base, see
[Share cluster defaults](../tutorials/intermediate/cluster-bases.md).

## Write the base

[`kubectl gs gitops add base`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-base/) creates a base for a
provider: `capa`, `capz` or `vsphere`. For example, for CAPZ, which also needs a region and your Azure subscription:

```sh
kubectl gs gitops add base --provider capz --region westeurope --azure-subscription-id SUBSCRIPTION_ID
```

It writes three files, into `bases/clusters/capz/template`:

- `cluster.yaml` with the `OCIRepository` of the `release-azure` chart and the `HelmRelease`;
- `cluster_config.yaml` with the default values, the region and the subscription among them;
- `kustomization.yaml`, which turns `cluster_config.yaml` into the `${cluster_name}-config` ConfigMap.

Move them up into `bases/clusters/capz`, where the [naming](../reference/repo-structure.md#naming) rules put a
provider's base:

```sh
mv bases/clusters/capz/template/* bases/clusters/capz/ && rmdir bases/clusters/capz/template
```

kubectl-gs 7.0.0 and newer put the `giantswarm.io/prevent-deletion` label on the `HelmRelease` and the
`OCIRepository`, and set `global.metadata.preventDeletion` in `cluster_config.yaml`. No release writes the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation, so add it to both, as the CAPA base has it, see
[Deletion protection](../explanation/deletion-protection.md). The command below sets the label as well, which an older
kubectl-gs doesn't write:

```sh
yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
  .metadata.labels["giantswarm.io/prevent-deletion"] = "true"' bases/clusters/capz/cluster.yaml
```

With kubectl-gs older than 7.0.0, also set `global.metadata.preventDeletion`, so the chart labels the `Cluster`:

```sh
yq -i '.global.metadata.preventDeletion = true' bases/clusters/capz/cluster_config.yaml
```

Compare the result with the [CAPA base](/bases/clusters/capa/), whose [readme](/bases/clusters/capa/readme.md) lists
where it differs from what the command writes on purpose, and copy the readme, which lists the variables the base
expects.

## Add the management cluster's values

The `HelmRelease` the command writes only reads `${cluster_name}-config`. Add the `cluster-app-installation-values`
entry in front of it, as the [CAPA base](/bases/clusters/capa/cluster.yaml) does, or the chart misses
`global.managementCluster` and `global.connectivity.baseDomain`:

```yaml
  valuesFrom:
    - kind: ConfigMap
      name: cluster-app-installation-values
      valuesKey: values.yaml
    - kind: ConfigMap
      name: ${cluster_name}-config
      valuesKey: values
```

Or with `yq`:

```sh
yq -i '(select(.kind == "HelmRelease") | .spec.valuesFrom) |=
  [{"kind": "ConfigMap", "name": "cluster-app-installation-values", "valuesKey": "values.yaml"}] + .' \
  bases/clusters/capz/cluster.yaml
```

On management clusters that run `kyverno-policies-ux` 0.15.1 or newer, its `prepend-cluster-app-config-map-hr` policy
prepends the same entry to a `HelmRelease` that lacks it. The explicit entry is for management clusters without that
policy, and it does no harm next to it: the policy only adds the entry when it is missing. See
[Values from the management cluster](/bases/clusters/capa/readme.md#values-from-the-management-cluster).

## Add a region

Leave the region out of the base: each cluster adds it with a region component, see
[Regions](../tutorials/intermediate/stages-and-regions.md#regions). For CAPZ, the command put the region into the base's
values, so take it out:

```sh
yq -i 'del(.global.providerSpecific.location)' bases/clusters/capz/cluster_config.yaml
```

The regions in this repository only set the AWS region, `global.providerSpecific.region`. `release-azure` reads the
region from `global.providerSpecific.location` instead, so create a region component that sets the location for your
Azure clusters, next to the AWS ones:

```sh
mkdir -p bases/environments/regions/westeurope
cp bases/environments/regions/eu_central/kustomization.yaml bases/environments/regions/westeurope/
cat <<'EOF' > bases/environments/regions/westeurope/region_config.yaml
global:
  providerSpecific:
    location: westeurope
EOF
```

The component appends its ConfigMap to the cluster's `valuesFrom` after the base's entries, see
[Cluster values](../reference/values.md#cluster-values). Then build a cluster from the base as the
[basic tutorial](../tutorials/basic/getting-started.md#3-create-a-workload-cluster) does, with
`bases/clusters/capz` and the new region.
