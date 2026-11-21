# management-clusters/MC_NAME/.sops.keys

The public halves of the SOPS keys, so anyone with the repository can encrypt a file for a cluster without being able
to decrypt it. Import a public key with `gpg --import`, or read an age recipient from its `.agekey.pub` file.

Flux doesn't apply this directory: it holds no Kubernetes objects. `.sops.yaml` at the repository root names the same
keys, by fingerprint or recipient, for each path.

## What's here

- `.sops.master.asc`: the management cluster's master key, a GPG key.
- `.sops.WC_NAME.asc`: the GPG key of `sops-gpg-wc-name`, which `WC_NAME_OUT_OF_BAND_FLUX_APP` decrypts with.
- `.sops.FROM_TEMPLATE_WC_NAME.asc`: the GPG key of `sops-gpg-from-template-wc-name`, which
  `WC_NAME_OUT_OF_BAND_NO_FLUX_APP` decrypts with.
- `.sops.WC_NAME.agekey.pub`: the age key of `sops-age-wc-name`, which `WC_NAME` decrypts with.

## When you copy it

Replace these with your own public keys, one file per key, and add a rule for each to `.sops.yaml`. Only public keys go
here. A private key never does: it goes, encrypted, into `secrets/` or an organisation's `namespace/secrets/`.

## Read more

- [SOPS keys](/docs/reference/sops-keys.md)
- [Keep secrets in the repository, encrypted](/docs/how-to/sops.md)
