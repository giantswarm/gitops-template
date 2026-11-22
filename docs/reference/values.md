# Values

A cluster's chart and an app's chart don't get their values from one file. They get them from several ConfigMaps and
Secrets, each written at a different level of the repository: the management cluster, a base, a region, a stage, the
cluster itself. This page lists those layers in the order Flux merges them, and the rules it merges them by.

A `HelmRelease` lists its layers in `spec.valuesFrom`. helm-controller reads them in that order and merges each one
over the result so far, then merges `spec.values` over all of them. So:

- **Later wins.** A key a later layer sets replaces the same key from an earlier one. `spec.values` beats every
  `valuesFrom` entry.
- **Maps merge.** Two layers that set different keys of the same map both count. A region's `global.nodePools.large`
  and a cluster's `global.nodePools.nodepool0` give the cluster both pools.
- **Lists are replaced.** A later layer that sets a list, such as `hostnames` or a node pool's `availabilityZones`,
  replaces the whole list. Nothing appends to it.
- **A later layer can't take a key away by leaving it out.** To remove a map key an earlier layer set, set it to
  `null`: Helm drops it when it merges the values with the chart's defaults.
- **A missing layer fails the release**, unless the entry has `optional: true`. The `HelmRelease` isn't `Ready` and
  retries until the ConfigMap or Secret exists, so the order Flux creates objects in doesn't matter.

Every ConfigMap and Secret a `HelmRelease` lists carries the `reconcile.fluxcd.io/watch: Enabled` label, so a change to
it reaches the release at once rather than at the next `interval`. CI fails for one without the label.

The layers get into `valuesFrom` with kustomize. A base lists its own. A component or a cluster adds one with a JSON
patch that appends, `op: add` with `path: /spec/valuesFrom/-`. Two rules follow from that:

- kustomize applies a `kustomization.yaml`'s `components` before its own `patches`, and the components in the order
  `components:` lists them. So the region comes before the node pool component, and both before the cluster's own
  values.
- A strategic merge patch can't add an entry: kustomize has no merge strategy for `HelmRelease`, so it falls back to a
  JSON merge patch, which replaces the whole list. A JSON patch with a fixed position, such as `/spec/valuesFrom/1`,
  is right only while the base has exactly the entries before it; when the base gains one, the layer silently moves.
  Append with `/-`.

## Cluster values

A cluster's `HelmRelease`, in the [cluster base](/bases/clusters/capa/cluster.yaml), reads these layers, first to last:

| # | Layer | Written by | Holds |
| --- | --- | --- | --- |
| 1 | ConfigMap `cluster-app-installation-values`, key `values.yaml` | the management cluster, see [Objects the management cluster provides](./repo-structure.md#objects-the-management-cluster-provides) | `global.managementCluster`, `global.connectivity.baseDomain` and what else the management cluster knows |
| 2 | ConfigMap `${cluster_name}-config` | the cluster base, from its `cluster_config.yaml`, or a [base with your own defaults](../tutorials/intermediate/cluster-bases.md#create-a-base-with-your-own-defaults), which replaces it whole | the defaults of every cluster made from the base |
| 3 | ConfigMap `${cluster_name}-region-config` | a region component in [bases/environments/regions](/bases/environments/regions/) | `global.providerSpecific.region`. Every cluster needs one |
| 4 | more components, optional, such as `${cluster_name}-region-node-pool-config` | a component, such as a region's [node_pool](/bases/environments/regions/eu_central/node_pool/) | an extra node pool |
| 5 | ConfigMap `${cluster_name}-cluster-userconfig` | the cluster, from `cluster/cluster_userconfig.yaml` and `cluster/patch_cluster_userconfig.yaml` | the cluster's own values |

A stage component, in [bases/environments/stages](/bases/environments/stages/), adds no layer. It pins versions
instead: it patches the `spec.ref` of the cluster's `OCIRepository`, which sets the release, and of the apps'.

A layer 2 that replaces the base's ConfigMap replaces all of it: a value it leaves out is gone, not inherited. That's
why a base with your own defaults starts from a copy of the base's `cluster_config.yaml`.

### A worked example

The [HELLO_APP_PROD_CLUSTER_EU_CENTRAL](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster/kustomization.yaml)
example lists the CAPA base, three components and a patch:

```yaml
components:
  - ../../../../../../../bases/environments/regions/eu_central
  - ../../../../../../../bases/environments/regions/eu_central/node_pool
  - ../../../../../../../bases/environments/stages/prod
patches:
  - path: patch_cluster_userconfig.yaml
    # ...
resources:
  - ../../../../../../../bases/clusters/capa
  - cluster_userconfig.yaml
  - apps/
```

Its `HelmRelease` ends up with five layers:

```yaml
valuesFrom:
  - kind: ConfigMap
    name: cluster-app-installation-values             # 1, from the base
    valuesKey: values.yaml
  - kind: ConfigMap
    name: hello-app-prod-euc-config                   # 2, from the base
    valuesKey: values
  - kind: ConfigMap
    name: hello-app-prod-euc-region-config            # 3, the first component
    valuesKey: values
  - kind: ConfigMap
    name: hello-app-prod-euc-region-node-pool-config  # 4, the second component
    valuesKey: values
  - kind: ConfigMap
    name: hello-app-prod-euc-cluster-userconfig       # 5, the cluster's own patch
    valuesKey: values
```

Layer 3 sets `global.providerSpecific.region: eu-central-1`. Layer 4 adds the node pool `large`, and layer 5 the node
pool `nodepool0`. `global.nodePools` is a map, so the cluster gets both pools. Had layer 5 also set
`large.availabilityZones`, its list would have replaced the region's three zones, not added to them.

That merge is why the CAPA base leaves `global.nodePools` out: the chart uses its default node pools only when
`global.nodePools` is empty, and a pool the base put in would turn up in every cluster next to the cluster's own. The
kind test checks the result for every example cluster (see [The kind test](./ci-checks.md#the-kind-test)).

To see what a cluster gets, render it as Flux does: see
[Render what Flux applies](../how-to/check-changes.md#render-what-flux-applies).

## App values

An app's `HelmRelease` reads these layers, first to last, as the [hello-world App Template](/bases/apps/hello-world/helm-release.yaml)
does:

| # | Layer | Written by | Optional |
| --- | --- | --- | --- |
| 1 | ConfigMap `${cluster_name}-cluster-values` | the management cluster, once the cluster exists: `baseDomain`, `provider` and more about the cluster | no |
| 2 | ConfigMap `${cluster_name}-APP_NAME-values` | the App Template, from its `default_config.yaml`, or a [stack](../tutorials/intermediate/stacks.md), which replaces it whole | no, but only an app from a template or a stack has it |
| 3 | ConfigMap `${cluster_name}-APP_NAME-user-values` | the cluster, from `override_config.yaml` in the app's directory | yes |
| 4 | Secret `${cluster_name}-APP_NAME-user-secrets` | the cluster, from a SOPS-encrypted `secret.enc.yaml` or an `ExternalSecret` | yes |

Layers 3 and 4 are what a cluster changes. Both are `optional: true`, so an app installs without them, and creating
the file is all it takes to add one: no patch to the `HelmRelease`. Layer 2 belongs to the template or the stack, and
changing it changes the app on every cluster that uses it.

The template's `HelmRelease` lists all four layers itself, rather than a shared patch adding layer 1 to every app: a
patch can't append to `valuesFrom` without a JSON patch per `HelmRelease`, as above.

For the steps, see [Change the values](../how-to/update-app.md#change-the-values) and
[Change secret values](../how-to/update-app.md#change-secret-values).
