# flux

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/flux`

flux-app, Giant Swarm's Flux chart, installed into the workload cluster, so the cluster runs Flux of its own. That
Flux reads your repository and applies the cluster's `out-of-band/` directory from inside the cluster.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_FLUX_APP-apps.yaml`, applies these objects into `org-<name>`
once the cluster is up. The `HelmRelease` installs the chart into the workload cluster's `flux-app` namespace through
the cluster's kubeconfig.

## What's here

- `oci-repository.yaml`: the flux-app chart and its version.
- `helm-release.yaml`: installs it, reading the cluster values and the values below.
- `configmap.yaml`: the values: the `GitRepository` the workload cluster's Flux reads, and the Kustomization that
  applies `out-of-band/`.

## When you copy it

Change the source in `configmap.yaml` to your repository and its credentials, and the Kustomization's `path` to your
cluster's `out-of-band/` directory. Don't keep credentials in plain text there: put them in a SOPS-encrypted
`${cluster_name}-flux-app-user-secrets` Secret, which the `HelmRelease` reads too.

The example pins flux-app 1.12.2, the version on the management clusters, which runs Flux 2.7.5. A new cluster needs
nothing more. A cluster that already runs flux-app older than 1.11.0 has to migrate its Flux objects on the way up:
the [flux-app changelog](https://github.com/giantswarm/flux-app/blob/main/CHANGELOG.md) for 1.11.0 says how, and
`migration.run: true` in the values does it in-line.

## Read more

- [Run Flux in the workload cluster](/docs/tutorials/advanced/out-of-band.md#run-flux-in-the-workload-cluster)
