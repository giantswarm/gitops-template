# management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP

A cluster without Flux of its own, which still gets objects applied straight into it: the management cluster's Flux
applies `out-of-band/` through the cluster's kubeconfig. It also shows ESO and SOPS side by side, secrets pushed into
the cluster, and application teams that deliver from their own repositories.

Three Flux Kustomizations, next to this directory in `workload-clusters/`, apply it:

- `WC_NAME_OUT_OF_BAND_NO_FLUX_APP.yaml` applies `cluster/` into `org-<name>`, and is Ready once Cluster API reports
  the cluster Available.
- `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml` then applies this directory into `org-<name>`, whose
  `kustomization.yaml` lists `apps/` and `teams/`.
- `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies `out-of-band/` into the workload cluster itself.

The first two decrypt with the GPG key `sops-gpg-from-template-wc-name`, from the organisation's `namespace/secrets/`.

## What's here

- `kustomization.yaml`: lists `apps/` and `teams/`, so neither `cluster/` nor `out-of-band/` is applied twice or to
  the wrong cluster.
- `cluster/`: the cluster, from the CAPA base and the `eu_central` region, with its own values in
  `cluster_userconfig.yaml` and `patch_cluster_userconfig.yaml`.
- `cluster/apps/`: the base apps, installed with the cluster. Its `kustomization.yaml` lists them.
- [`cluster/apps/envoy-gateway-from-template/`](cluster/apps/envoy-gateway-from-template/): the envoy-gateway stack.
- `apps/`: the secondary apps, installed once the cluster is up. Its `kustomization.yaml` lists them.
- `apps/hello-world/`: hello-world written out in full, with an `externalsecret.yaml` that reads its secret values
  from your secret manager.
- [`apps/hello-world-automatic-updates/`](apps/hello-world-automatic-updates/): hello-world following a version range.
- [`apps/hello-world-from-template/`](apps/hello-world-from-template/): hello-world from its App Template.
- [`apps/workload-cluster-secrets/`](apps/workload-cluster-secrets/): secrets pushed into the cluster through a store
  in Git.
- [`apps/pushed-password/`](apps/pushed-password/): a password pushed through the store Kyverno makes.
- [`teams/`](teams/): application teams whose Flux runs on the management cluster.
- `out-of-band/`: what the `-direct` Kustomization applies to the workload cluster. It has no `kustomization.yaml`,
  so Flux takes every YAML file below it.
- `out-of-band/configmaps/`: an example ConfigMap for the `default` namespace of the workload cluster.
- [`out-of-band/teams/`](out-of-band/teams/): the teams' namespaces and rights in the workload cluster.

## When you copy it

Copy the directory and its three Kustomizations, rename them after your cluster, and set `cluster_name` in all three,
`release` in the first two, the health check's cluster name in `WC_NAME_OUT_OF_BAND_NO_FLUX_APP.yaml`, and the `-direct`
Kustomization's kubeconfig Secret. Change the `-direct` Kustomization's name in the `dependsOn` of
`teams/hello-team/flux-kustomization.yaml` too, where a `TODO` marks it. Give the cluster its own SOPS key:

- add its public half to `.sops.keys/` and a rule to `.sops.yaml`;
- add its private half, encrypted with the master key, to the organisation's `namespace/secrets/` and to `resources:`
  in the `kustomization.yaml` there;
- set `spec.decryption.secretRef.name` in the cluster's Kustomization and its apps Kustomization to that Secret's name;
  the `-direct` one decrypts nothing;
- encrypt `cluster/apps/envoy-gateway-from-template/secret.enc.yaml` again with it, or delete it and its line in that
  directory's `kustomization.yaml`. Point the `ExternalSecret`s at your own store. Delete the examples
you don't need, with their lines in the `kustomization.yaml` that lists them. `teams/` needs the `-direct`
Kustomization, and `apps/pushed-password/` the store from the organisation's `multicluster/secret-stores/`.

## Read more

- [Add the -direct Kustomization](/docs/tutorials/advanced/out-of-band.md#add-the--direct-kustomization)
- [SOPS and ESO in one repository](/docs/explanation/secrets.md)
- [Teams tutorial](/docs/tutorials/advanced/teams.md)
