# workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP

A cluster with Flux of its own. The management cluster installs flux-app into the workload cluster, and that Flux
applies `out-of-band/` from inside the cluster. Use it for what you'd rather the workload cluster reconciled itself.
The cluster also shows App Templates, a stack as base apps, and an app that updates itself.

Two Flux Kustomizations, next to this directory in `workload-clusters/`, apply it into `org-<name>`. Both decrypt with
the GPG key `sops-gpg-wc-name`, from the organisation's `namespace/secrets/`:

- `WC_NAME_OUT_OF_BAND_FLUX_APP.yaml` applies `cluster/`, and is Ready once Cluster API reports the cluster Available.
- `WC_NAME_OUT_OF_BAND_FLUX_APP-apps.yaml` then applies this directory, whose `kustomization.yaml` lists only `apps/`.

## What's here

- `kustomization.yaml`: lists `apps/`, so neither `cluster/` nor `out-of-band/` is applied twice or to the wrong
  cluster.
- `cluster/`: the cluster, from the CAPA base and the `eu_central` region, with its own values in
  `cluster_userconfig.yaml` and `patch_cluster_userconfig.yaml`.
- `cluster/apps/`: the base apps, installed with the cluster. Its `kustomization.yaml` lists them.
- [`cluster/apps/envoy-gateway-from-template/`](cluster/apps/envoy-gateway-from-template/): the envoy-gateway stack.
- `apps/`: the secondary apps, installed once the cluster is up. Its `kustomization.yaml` lists them.
- [`apps/flux/`](apps/flux/): flux-app in the workload cluster.
- `apps/hello-world/`: hello-world written out in full, as an `oci-repository.yaml` and a `helm-release.yaml`.
- [`apps/hello-world-automatic-updates/`](apps/hello-world-automatic-updates/): hello-world following a version range.
- [`apps/hello-world-from-template/`](apps/hello-world-from-template/): hello-world from its App Template.
- `out-of-band/`: what the workload cluster's own Flux applies. The management cluster never does.
- `out-of-band/configmaps/`: an example ConfigMap for the `default` namespace of the workload cluster.

## When you copy it

Copy the directory and its two Kustomizations, rename them after your cluster, and set `cluster_name`, `release` and
the health check's cluster name. Give the cluster its own SOPS key, and encrypt the `secret.enc.yaml` files again with
it. Point flux-app's values at your repository, and the path at this cluster's `out-of-band/`.

## Read more

- [Run Flux in the workload cluster](/docs/tutorials/advanced/out-of-band.md#run-flux-in-the-workload-cluster)
- [Add an app](/docs/how-to/add-app.md)
