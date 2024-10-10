# Input Variables

Expected variables are in the table below.

| Variable | Expected Value |
| :--: | :--: |
| `cluster_description` | User Friendly name for the cluster |
| `cluster_name` | Unique name of the Workload Cluster, MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `cluster_release` | Giant Swarm Release to use, reference the [Releases repo](https://github.com/giantswarm/releases) for more insight on releases |
| `organization` | Organization name, the `org-` prefix MUST not be part of it and MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |