# teams

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/teams`

Application teams that deliver to this cluster from their own repositories, with Flux on the management cluster
applying their work. The platform team owns these objects, and each team owns its repository. Each team has the same
shape, so this README covers them.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies this directory into
`org-<name>`. Each team's Flux Kustomization then applies the team's repository into the team's namespace in the
workload cluster, through the cluster's kubeconfig.

## What's here

- `kustomization.yaml`: lists the teams.
- [`hello-team/`](hello-team/): the example team.
  - `git-repository.yaml`: the team's repository and the branch or tag Flux applies.
  - `flux-kustomization.yaml`: applies the team's directory into the `hello-team` namespace, as the organisation's
    `automation` ServiceAccount. It waits for the cluster's `-direct` Kustomization, which creates that namespace.
  - `kustomization.yaml`: lists the two.

The team's namespace and its rights there are in [`out-of-band/teams/`](../out-of-band/teams/).

## When you copy it

Copy `hello-team/` once per team, and set the repository, the ref, the `path` and the `targetNamespace`. Add the team
to `kustomization.yaml`, and its namespace and RoleBinding to `out-of-band/teams/`. Keep `targetNamespace`: it keeps
the team in its own namespace.

## Read more

- [Flux on the management cluster](/docs/tutorials/advanced/teams.md#add-a-team-with-flux-on-the-management-cluster)
- [Remove a team](/docs/tutorials/advanced/teams.md#remove-a-team)
