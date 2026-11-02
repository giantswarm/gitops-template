# Input Variables

This base deploys a cluster with the `release-aws` chart. Its chart version is the Giant Swarm release version, so
the release lives in git and you upgrade the cluster by changing `release`. It's an overlay of the
[template](../template) base that only changes the chart name and version.

Use it when the `cluster` catalog has a `release-aws` chart for your release. That's every release from v34.0.0 on,
and v31.2.0, v32.3.0 and v33.3.0. For other releases, or for a Release CR you created by hand, use the template base.

Expected variables are in the table below.

| Variable | Expected Value |
| :--: | :--: |
| `cluster_description` | User Friendly name for the cluster |
| `cluster_name` | Unique name of the Workload Cluster, MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `organization` | Organization name, the `org-` prefix MUST not be part of it and MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `release` | Giant Swarm release version without the `v` prefix, for example `36.2.0` |
