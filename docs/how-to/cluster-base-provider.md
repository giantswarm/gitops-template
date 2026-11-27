# Create a cluster base for another provider

The template ships one provider's base, [bases/clusters/capa](/bases/clusters/capa/), for AWS. For clusters on another
provider, such as Azure with CAPZ, create a base for it next to the CAPA one. `kubectl gs gitops add base` writes most
of it; this page covers the rest. To build a base with your own defaults on top of a provider's base, see
[Share cluster defaults](../tutorials/intermediate/cluster-bases.md). The base is the first thing that differs on
another provider, and not the last: [Run the template on another provider](./other-providers.md) lists the others,
and says how to write a base for Cloud Director, which the command doesn't know.

## Write the base

[`kubectl gs gitops add base`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-base/) creates a base for a
provider: `capa`, `capz` or `vsphere`. For example, for CAPZ, which also needs a region and your Azure subscription:

```sh
kubectl gs gitops add base --provider capz --region westeurope --azure-subscription-id SUBSCRIPTION_ID
```

It writes three files, into `bases/clusters/capz`, where the [naming](../reference/repo-structure.md#naming) rules put
a provider's base, and the path `kubectl gs gitops add workload-cluster --base` takes:

- `cluster.yaml` with the `OCIRepository` of the `release-azure` chart and the `HelmRelease`, both protected with the
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the `giantswarm.io/prevent-deletion` label, see
  [Deletion protection](../explanation/deletion-protection.md);
- `cluster_config.yaml` with the default values, the region and the subscription among them, and
  `global.metadata.preventDeletion: true`, so the chart labels the `Cluster` too;
- `kustomization.yaml`, which turns `cluster_config.yaml` into the `${cluster_name}-config` ConfigMap.

That's what kubectl-gs 8.0.0 and newer write. Older releases write the base into `bases/clusters/capz/template`, without
the annotation, and releases before 7.0.0 also leave out the label and `preventDeletion`. Move the files up a level and
add what's missing:

```sh
mv bases/clusters/capz/template/* bases/clusters/capz/ && rmdir bases/clusters/capz/template
yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
  .metadata.labels["giantswarm.io/prevent-deletion"] = "true"' bases/clusters/capz/cluster.yaml
yq -i '.global.metadata.preventDeletion = true' bases/clusters/capz/cluster_config.yaml
```

Compare the result with the [CAPA base](/bases/clusters/capa/), whose [readme](/bases/clusters/capa/readme.md) lists
where it deliberately differs from what the command writes, and copy the readme, which lists the variables the base
expects.

## Add the management cluster's values

From kubectl-gs 8.0.0 on, the `HelmRelease` reads `cluster-app-installation-values` before `${cluster_name}-config`,
as the [CAPA base](/bases/clusters/capa/cluster.yaml) does, and there's nothing to add. An older release's `HelmRelease`
reads only `${cluster_name}-config`: add the entry in front of it, or the chart misses `global.managementCluster` and
`global.connectivity.baseDomain`:

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
