# teams

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/out-of-band/teams`

An application team's scope inside the workload cluster, for a team whose Flux runs there: its namespace, the rights
to it, and the `GitRepository` and Kustomization that deliver from the team's own repository. The platform team owns
these objects.

The workload cluster's own Flux, which [`apps/flux/`](../../apps/flux/) installs, pulls `out-of-band/` and applies
this directory with it. The same Flux then reconciles the team's Kustomization. The management cluster never applies
it.

## What's here

- `hello-team-wc.yaml`: the `hello-team-wc` namespace, a ServiceAccount and RoleBinding for it, and the team's
  `GitRepository` and Kustomization, which runs as that ServiceAccount.

## When you copy it

One file per team. Change the namespace, the repository, the ref and the `path` in the team's repository. Keep the
`admin` ClusterRole bound in a RoleBinding, not a ClusterRoleBinding: a team gets everything in its own namespace and
nothing anywhere else.

This mode needs Flux in the workload cluster, as the `GitRepository` and the Kustomization are Flux's kinds. For a
cluster without Flux of its own, deliver the team from the management cluster, as
[`WC_NAME_OUT_OF_BAND_NO_FLUX_APP`](../../../WC_NAME_OUT_OF_BAND_NO_FLUX_APP/teams/) does.

## Read more

- [Two modes](/docs/tutorials/advanced/teams.md#two-modes)
- [Flux in the workload cluster](/docs/tutorials/advanced/teams.md#add-a-team-with-flux-in-the-workload-cluster)
