# management-clusters/MC_NAME/secrets

The management cluster's master key, `sops-gpg-master`, as a Secret encrypted with the master key itself. With it,
Flux decrypts the encrypted files that the management cluster's Kustomization and the organisations' namespace
Kustomizations apply, the workload clusters' keys among them.

The management cluster's Kustomization, in `../MC_NAME.yaml`, applies this directory into the `default` namespace. You
also apply the Secret by hand once, before that Kustomization can decrypt anything.

## What's here

- `MC_NAME.gpgkey.enc.yaml`: the master key's private key, encrypted.
- `kustomization.yaml`: lists the Secret, and marks it `kustomize.toolkit.fluxcd.io/prune: disabled` and
  `giantswarm.io/prevent-deletion: "true"`. Deleting the key stops GitOps for the whole management cluster, so Flux
  never deletes it, and nobody can until the label is removed.

## When you copy it

Write your own master key here, encrypt it, and rename the file after your cluster. Add the file to `resources:` in
`kustomization.yaml` in the same commit: Flux only applies what's listed. Keep the annotation and the label.

## Read more

- [The master key](/docs/reference/sops-keys.md#the-master-key)
- [The protected objects](/docs/explanation/deletion-protection.md#the-protected-objects)
