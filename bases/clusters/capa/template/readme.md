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
