# WC_NAME

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME`

The plain example: one cluster on AWS from the CAPA cluster base, with one secondary app whose values are encrypted
with SOPS and the cluster's own age key. Start here if you want a cluster and nothing clever.

Two Flux `Kustomization`s, next to this directory in `workload-clusters/`, apply it into `org-<name>`. Both decrypt with
the age key `sops-age-wc-name`, from the organisation's `namespace/secrets/`:

- `WC_NAME.yaml` applies `cluster/`, and is `Ready` once Cluster API reports the cluster's control plane available and
  reachable.
- `WC_NAME-apps.yaml` then applies this directory, whose `kustomization.yaml` lists only `apps/`.

## What's here

- `kustomization.yaml`: lists `apps/`, so the apps `Kustomization` never applies `cluster/` a second time.
- `cluster/`: the cluster.
  - `kustomization.yaml`: the CAPA base, the `eu_central` region, and a patch with the cluster's own values.
  - `cluster_userconfig.yaml`: the cluster's own values, here a node pool.
  - `patch_cluster_userconfig.yaml`: appends those values to the cluster `HelmRelease`'s `valuesFrom`, last.
- `apps/`: the secondary apps, installed once the cluster is up.
  - `kustomization.yaml`: lists the apps, puts them in `org-<name>`, labels them with the cluster, and patches every
    `HelmRelease` with the cluster's kubeconfig.
  - `patch_cluster_config.yaml`: that patch.
- `apps/cert-manager/`: cert-manager, as an `oci-repository.yaml` and a `helm-release.yaml`, with
  `secret.enc.yaml`, its `-user-secrets` values encrypted with the cluster's age key.

## When you copy it

Copy the directory and its two `Kustomization`s, rename them after your cluster, and set `cluster_name` in both, and
`release` and the health check's cluster name in `WC_NAME.yaml`, the only one that installs the cluster. Give the
cluster its own key:

- add its public half to `.sops.keys/` and a rule to `.sops.yaml`;
- add its private half, encrypted with the master key, to the organisation's `namespace/secrets/` and to `resources:`
  in the `kustomization.yaml` there;
- set `spec.decryption.secretRef.name` in both `Kustomization`s to that Secret's name;
- encrypt `apps/cert-manager/secret.enc.yaml` again with it, or delete the file.

Pick your region in `cluster/kustomization.yaml`. Keep the split between `cluster/` and `apps/`: the apps need a running
cluster. List the cluster's `Kustomization`s in `workload-clusters/kustomization.yaml` and in the organisation's commit
status `Alert`, as [`workload-clusters/README.md`](../README.md#when-you-copy-it) says.

## Read more

- [3. Create a workload cluster](/docs/tutorials/basic/getting-started.md#3-create-a-workload-cluster)
- [Add a workload cluster key (age)](/docs/how-to/sops.md#add-a-workload-cluster-key-age)
- [Encrypt an app's values](/docs/how-to/sops.md#encrypt-an-apps-values)
