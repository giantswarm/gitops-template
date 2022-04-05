# Input Variables

Expected variables are in the table below.

| Variable | Expected Value |
| :--: | :--: |
| `cluster_name` | Unique name of the Workload Cluster, MUST comply with the
[Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `organization` | Organization name, the `org-` prefix MUST not be part of it and MUST comply with the
[Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
| `cluster_release` | Cluster App version, reference the
[Cluster Openstack](https://github.com/giantswarm/cluster-openstack/releases) for more insight on releases |
| `default_apps_release` | Defaults Apps App version, reference the
[Default Apps for Openstack](https://github.com/giantswarm/default-apps-openstack/releases) for more insight on
releases |
