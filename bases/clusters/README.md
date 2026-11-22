# clusters

`bases/clusters`

Cluster bases: what every workload cluster of one provider has in common, so a cluster's own directory only holds
what makes it different. There's one directory per provider.

Nothing applies this directory directly. A cluster's `cluster/kustomization.yaml` lists its base under `resources:`,
and the cluster's Flux `Kustomization` applies it into the organisation's namespace, `org-<name>`, filling in
`${cluster_name}`, `${cluster_description}`, `${organization}` and `${release}`.

## What's here

- [`capa/`](capa/): clusters on AWS with Cluster API, from the `release-aws` chart. Its [readme](capa/readme.md)
  lists the variables and the order of the values.

A cluster adds its region, and optionally a stage, as Components from
[`bases/environments`](../environments/), and its own values with a patch next to the base.

## When you copy it

Leave `capa/` as it is and point your clusters at it. For another provider, add a directory next to it with the same
three files. Keep the deletion protection on the `HelmRelease` and `OCIRepository`, and keep
`cluster-app-installation-values` first in `valuesFrom`.

## Read more

- [Cluster bases tutorial](/docs/tutorials/intermediate/cluster-bases.md)
- [Create a cluster base for another provider](/docs/how-to/cluster-base-provider.md)
