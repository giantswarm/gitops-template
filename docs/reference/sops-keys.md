# SOPS keys

If you keep secrets in the repository, you encrypt them with [SOPS](https://github.com/getsops/sops) and GPG or
[age](https://github.com/FiloSottile/age) keys, and Flux decrypts them when it applies them. This page explains which
keys there are, where they live and which files each one decrypts. For the steps, see [Getting started with SOPS](../getting-started-sops.md).

## The master key

Each management cluster has its own GPG key pair, the master key:

- Its public key is in `management-clusters/MC_NAME/.sops.keys`, unencrypted.
- Its private key is in the `MC_NAME.gpgkey.enc.yaml` Secret, encrypted with the master key itself.

Flux uses it to decrypt the files that the `MC_NAME.yaml` Kustomization applies, everything up to and including the
`workload-clusters` directory. Use it to encrypt the other keys, so you can keep them in the repository too.

## Workload cluster keys

To encrypt files of a workload cluster, add a key pair for it:

- Its public key goes into `.sops.keys`, unencrypted.
- Its private key goes into the `WC_NAME.gpgkey.enc.yaml` Secret in the management cluster's `secrets` directory,
  encrypted with the master key.

The cluster's two Kustomizations reference that Secret in `spec.decryption` and use it to decrypt what they apply:
`WC_NAME.yaml` the `WC_NAME/mapi/cluster` directory, and `WC_NAME-apps.yaml` the rest of `WC_NAME/mapi`.

```text
                MC_NAME.yaml
                     |
                 (creates) <---(decrypts with)--- MC_NAME.gpgkey.enc.yaml
                     |
  OTHER_RESOURCES <--+--> WC_NAME.yaml, WC_NAME-apps.yaml
                               |
                           (creates) <---(decrypts with)--- WC_NAME.gpgkey.enc.yaml
                               |
                               ˅
                         OTHER_RESOURCES
```

## age keys

A workload cluster key can be an age key instead of a GPG key; age keys are simpler to create and handle. The
master key stays a GPG key, because `kubectl gs gitops add management-cluster` creates one, and it encrypts the
age key like the GPG keys:

- Its public key goes into `.sops.keys` as `.sops.WC_NAME.agekey.pub`, unencrypted.
- Its private key goes into the `WC_NAME.agekey.enc.yaml` Secret in the management cluster's `secrets` directory,
  under a key that ends in `.agekey`, encrypted with the master key.

The cluster's Kustomizations name that Secret in `spec.decryption`. In the example tree, the `WC_NAME` cluster
uses an age key: `WC_NAME.yaml` and `WC_NAME-apps.yaml` decrypt with the `sops-age-wc-name` Secret, and
`WC_NAME-apps.yaml` decrypts `mapi/apps/cert-manager/secret.enc.yaml` with it. For the steps, see
[Create an age key pair](../add_wc_structure.md#create-an-age-key-pair-optional-step).

A Kustomization reads one Secret. To decrypt with a GPG key and an age key, put both private keys into it.

## Encryption rules

`.sops.yaml` at the repository root tells SOPS which key encrypts which files. With one key for the management
cluster, a GPG key for one workload cluster and an age key for another, it looks like this:

```yaml
creation_rules:
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/secrets/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000001
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/organizations/demo-gitops/workload-clusters/demo0/mapi/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000002
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/organizations/demo-gitops/workload-clusters/demo1/mapi/.*\.enc\.yaml
    age: age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq
```

## More keys

You can add more private keys to either Secret, for example one key for an organization and one for each app. Each
key needs its own rule in `.sops.yaml`:

```yaml
creation_rules:
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/secrets/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000001 # master key
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/organizations/demo-gitops/secrets/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000002 # organization key
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/organizations/demo-gitops/workload-clusters/demo0/mapi/apps/app1/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000003 # app1 key
```

The organization key decrypts files that `MC_NAME.yaml` applies, so it goes into the master Secret. The app key
goes into the workload cluster's Secret:

```yaml
## MC_NAME.gpgkey.enc.yaml ##
apiVersion: v1
data:
  demomc.master.asc: SOPS_ENCRYPTED_BASE64_ENCODED_MASTER_PRIVATE_KEY #01
  demomc.demo-gitops.asc: SOPS_ENCRYPTED_BASE64_ENCODED_ORGANIZATION_PRIVATE_KEY #02
kind: Secret
metadata:
  name: sops-gpg-master
```

```yaml
## WC_NAME.gpgkey.enc.yaml ##
apiVersion: v1
data:
  demo0.app1.asc: SOPS_ENCRYPTED_BASE64_ENCODED_APP1_PRIVATE_KEY #03
kind: Secret
metadata:
  name: sops-gpg-demo0
```
