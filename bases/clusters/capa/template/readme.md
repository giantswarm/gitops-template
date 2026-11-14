# Input Variables

This base deploys a cluster with the `release-aws` chart, as a Flux `OCIRepository` and `HelmRelease`. The chart
version is the Giant Swarm release version, so the release lives in git and you upgrade the cluster by changing
`release`.

To add your own values, add a ConfigMap with a `values` key next to the base, and a patch that appends it to the
`HelmRelease`'s `valuesFrom`. See the [WC_NAME](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/mapi/cluster/) example.

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

## Differences to `kubectl gs gitops add base`

This base has the files `kubectl gs gitops add base --provider capa` writes: `kustomization.yaml`, `cluster.yaml` with
the `OCIRepository` and the `HelmRelease`, and `cluster_config.yaml` with the cluster values. The resources are the
same. `cluster_config.yaml` differs on purpose:

- It sets `global.metadata.description` to `${cluster_description}`. The workload cluster `Kustomization`s, the ones in
  this repository and the ones `kubectl gs gitops add workload-cluster` writes, substitute `cluster_description`, and
  the table above documents it. Without this line the variable would have no effect.
- It leaves out `global.nodePools: {nodepool0: {}}`. The chart only uses its default node pools when `global.nodePools`
  is empty, and Flux and Helm merge maps from every `valuesFrom` entry, so an overlay can't take a node pool out that
  the base puts in. With `nodepool0` in the base, a cluster that defines its own node pools, like the
  [regions](/bases/environments/regions/) and the `WC_NAME` examples do, would get an extra `nodepool0` as well.
