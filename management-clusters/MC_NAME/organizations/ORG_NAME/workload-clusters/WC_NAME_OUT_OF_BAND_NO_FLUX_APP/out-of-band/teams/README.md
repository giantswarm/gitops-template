# teams

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band/teams`

The application teams' scope inside the workload cluster: each team's namespace, and the rights to it. The platform
team owns these objects.

The cluster's `-direct` Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml`, applies this directory straight
into the workload cluster, through its kubeconfig.

## What's here

- `hello-team.yaml`: for a team whose Flux runs on the management cluster, in [`teams/`](../../teams/). The
  `hello-team` namespace, and a RoleBinding that makes the organisation's `automation` ServiceAccount admin there,
  which the team's Kustomization runs as.

## When you copy it

One file per team. Change the namespace. Keep the `admin` ClusterRole bound in a RoleBinding, not a
ClusterRoleBinding: a team gets everything in its own namespace and nothing anywhere else.

This cluster runs no Flux of its own, so it has no team whose Flux runs in the workload cluster: that mode's
`GitRepository` and Kustomization are Flux's kinds, which the cluster doesn't know. Its example is in
[`WC_NAME_OUT_OF_BAND_FLUX_APP`](../../../WC_NAME_OUT_OF_BAND_FLUX_APP/out-of-band/teams/).

## Read more

- [Two modes](/docs/tutorials/advanced/teams.md#two-modes)
- [Flux on the management cluster](/docs/tutorials/advanced/teams.md#add-a-team-with-flux-on-the-management-cluster)
