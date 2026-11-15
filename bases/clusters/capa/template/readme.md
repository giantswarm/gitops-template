# Input Variables

This base deploys a cluster with the `release-aws` chart, as a Flux `OCIRepository` and `HelmRelease`. The chart
version is the Giant Swarm release version, so the release lives in git and you upgrade the cluster by changing
`release`.

The `HelmRelease` reads its values from these ConfigMaps, in this order. Flux merges them, and later entries win:

1. `cluster-app-installation-values`, key `values.yaml`: the management cluster's values. See
   [Values from the management cluster](#values-from-the-management-cluster).
1. `${cluster_name}-config`: the values of this base, from `cluster_config.yaml`.

The cluster appends the rest in its own kustomization:

1. `${cluster_name}-region-config`: the cluster's region, from a [region](/bases/environments/regions/) component.
   Every cluster needs one. Without `global.providerSpecific.region`, the chart takes the region of the management
   cluster's nodes, so the cluster would be created in the management cluster's region. `tools/validate-helm-values`
   fails for a cluster without a region.
1. Optionally more components, such as a region's extra node pool.
1. Your own values, last. Add a ConfigMap with a `values` key next to the base, and a patch that appends it to the
   `HelmRelease`'s `valuesFrom`. See the [WC_NAME](
   /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/mapi/cluster/) example.

List the components under `components:` in the kustomization that has the patch with your own values. kustomize applies
a kustomization's components before its own patches, so the region comes before your values, and the components come in
the order you list them. `kubectl gs gitops add workload-cluster` writes this kustomization with the patch; add the
`components:` list to it.

Use it when there's a `release-aws` chart for your release. That's every release from v34.0.0 on, and v31.2.0,
v32.3.0 and v33.3.0. Other releases, and Release CRs created by hand, need the `cluster-aws` chart as an App CR, which
this repository no longer supports.

Expected variables are in the table below.

| Variable | Expected Value |
| :--: | :--: |
| `cluster_description` | User Friendly name for the cluster |
| `cluster_name` | Unique name of the Workload Cluster, MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `organization` | Organization name, the `org-` prefix MUST not be part of it and MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `release` | Giant Swarm release version without the `v` prefix, for example `36.2.0` |

## Values from the management cluster

The `release-aws` chart needs values that only the management cluster knows, such as `global.managementCluster` and
`global.connectivity.baseDomain`. The base doesn't set them. It reads them from the `cluster-app-installation-values`
ConfigMap, which every Giant Swarm management cluster has:

- Giant Swarm creates it in the `giantswarm` namespace. Its `values.yaml` key holds `global.managementCluster` and
  `global.connectivity.baseDomain`. Some installations add more keys, such as container registry mirrors.
- A [Kyverno](https://kyverno.io/) policy, `sync-cluster-app-configmap-to-org-namespaces`, copies it into every `org-*`
  namespace, where the cluster's `HelmRelease` can read it. The policy is a
  [generate rule](https://kyverno.io/docs/policy-types/cluster-policy/generate/) that clones the ConfigMap from the
  `giantswarm` namespace with `synchronize: true`, so Kyverno creates the copy in every new organization namespace and
  updates the copies when the original changes. Giant Swarm ships the policy with `kyverno-policies-ux` 0.14.0 and
  newer. On a management cluster with an older `kyverno-policies-ux`, the organization namespaces don't have the
  ConfigMap, and every cluster `HelmRelease` made from this base fails. Flux reports
  `could not resolve ConfigMap chart values reference '<namespace>/cluster-app-installation-values' with key
  'values.yaml': configmaps "cluster-app-installation-values" not found`. The entry is required on purpose: a cluster
  without the management cluster's values must not be installed.

The ConfigMap isn't in this repository, and you don't create it. Clusters created as App CRs get the same ConfigMap
through the App's `extraConfigs`.

Values in the repository go after it in `valuesFrom`, so a cluster can still override any of them.

`kyverno-policies-ux` 0.15.1 and newer also has a `MutatingPolicy`, `prepend-cluster-app-config-map-hr`. It prepends
the same `cluster-app-installation-values` entry to the `valuesFrom` of a `HelmRelease` in an `org-*` namespace whose
`OCIRepository` serves a Giant Swarm cluster chart such as `release-aws`, unless the entry is already there. (0.15.0
added the policy, but only for the `cluster-*` charts.) The base lists the entry itself for management clusters that
don't run the policy. Where the policy runs, it finds the entry and leaves the `HelmRelease` as it is, so the explicit
entry does no harm.

## Differences to `kubectl gs gitops add base`

This base has the files `kubectl gs gitops add base --provider capa` writes: `kustomization.yaml`, `cluster.yaml` with
the `OCIRepository` and the `HelmRelease`, and `cluster_config.yaml` with the cluster values. The resources are the
same, but the `HelmRelease` reads more values, see below. `cluster_config.yaml` differs on purpose:

- It sets `global.metadata.description` to `${cluster_description}`. The workload cluster `Kustomization`s, the ones in
  this repository and the ones `kubectl gs gitops add workload-cluster` writes, substitute `cluster_description`, and
  the table above documents it. Without this line the variable would have no effect.
- It leaves out `global.nodePools: {nodepool0: {}}`. The chart only uses its default node pools when `global.nodePools`
  is empty, and Flux and Helm merge maps from every `valuesFrom` entry, so an overlay can't take a node pool out that
  the base puts in. With `nodepool0` in the base, a cluster that defines its own node pools, like the
  [regions](/bases/environments/regions/) and the `WC_NAME` examples do, would get an extra `nodepool0` as well.

The `HelmRelease` differs as well. `kubectl gs gitops add base` (v6.0.4) only reads `${cluster_name}-config`, so a
cluster made from its base gets no `global.managementCluster` or `global.connectivity.baseDomain`, which `release-aws`
requires. This base adds `cluster-app-installation-values` before it, with the [values from the management
cluster](#values-from-the-management-cluster). The region isn't in the base: each cluster adds it with a component.

If you create a base with `kubectl gs gitops add base`, add the entry to its `HelmRelease`, see
[Create a base for another provider](/docs/guides/cluster-templates.md#create-a-base-for-another-provider-optional).
