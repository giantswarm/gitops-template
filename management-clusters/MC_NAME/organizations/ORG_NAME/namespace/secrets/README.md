# secrets

`management-clusters/MC_NAME/organizations/ORG_NAME/namespace/secrets`

The SOPS keys the organisation's workload clusters decrypt their files with, as Secrets encrypted with the management
cluster's master key. A Flux `Kustomization` reads its decryption Secret from its own namespace, so the keys live here,
next to the clusters' `Kustomization`s.

The organisation's namespace `Kustomization`, in `../../namespace.yaml`, applies this directory into `org-<name>`, and
decrypts the keys with the master key.

## What's here

- `WC_NAME.agekey.enc.yaml`: the age key `sops-age-wc-name`, for `WC_NAME`.
- `WC_NAME.gpgkey.enc.yaml`: the GPG key `sops-gpg-wc-name`, for `WC_NAME_OUT_OF_BAND_FLUX_APP`.
- `FROM_TEMPLATE_WC_NAME.gpgkey.enc.yaml`: the GPG key `sops-gpg-from-template-wc-name`, for
  `WC_NAME_OUT_OF_BAND_NO_FLUX_APP`.
- `kustomization.yaml`: lists the keys, and marks them `kustomize.toolkit.fluxcd.io/prune: disabled` and
  `giantswarm.io/prevent-deletion: "true"`. Deleting a key stops GitOps for its clusters.

## When you copy it

Replace the keys with your own clusters' keys, one file per key, and add each to `resources:` in `kustomization.yaml`
in the same commit. Write `metadata.namespace: org-<name>` with the real name before you encrypt a key: changing an
encrypted file afterwards breaks its MAC, and `sops` can no longer decrypt it to change it or rotate its key. Keep the
annotation and the label.

## Read more

- [Workload cluster keys](/docs/reference/sops-keys.md#workload-cluster-keys)
- [Add a workload cluster key (age)](/docs/how-to/sops.md#add-a-workload-cluster-key-age)
- [Remove the cluster's keys](/docs/how-to/delete-cluster.md#remove-the-clusters-keys)
