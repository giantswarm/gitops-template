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
- `hello-team-wc.yaml`: for a team whose Flux runs in the workload cluster. The `hello-team-wc` namespace, a
  ServiceAccount and RoleBinding for it, and the team's `GitRepository` and Kustomization, which the workload
  cluster's Flux reconciles.

## When you copy it

One file per team. Change the namespace, the repository, the ref and, for a team with Flux in the workload cluster, the
`path` in its repository. Keep the `admin` ClusterRole bound in a RoleBinding, not a ClusterRoleBinding: a team gets
everything in its own namespace and nothing anywhere else. The second mode needs Flux in the workload cluster.

## Read more

- [Two modes](/docs/tutorials/advanced/teams.md#two-modes)
- [Flux in the workload cluster](/docs/tutorials/advanced/teams.md#add-a-team-with-flux-in-the-workload-cluster)
