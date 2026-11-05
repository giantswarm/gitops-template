# SOPS keys

If you keep secrets in the repository, you encrypt them with [SOPS](https://github.com/getsops/sops) and GPG keys,
and Flux decrypts them when it applies them. This page explains which keys there are, where they live and which
files each one decrypts. For the steps, see [Getting started with SOPS](../getting-started-sops.md).

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

The `WC_NAME.yaml` Kustomization references that Secret and uses it to decrypt everything in the `WC_NAME`
directory.

```text
                MC_NAME.yaml
                     |
                 (creates) <---(decrypts with)--- MC_NAME.gpgkey.enc.yaml
                     |
  OTHER_RESOURCES <--+--> WC_NAME.yaml
                               |
                           (creates) <---(decrypts with)--- WC_NAME.gpgkey.enc.yaml
                               |
                               ˅
                         OTHER_RESOURCES
```

## Encryption rules

`.sops.yaml` at the repository root tells SOPS which key encrypts which files. With one key for the management
cluster and one for a workload cluster, it looks like this:

```yaml
creation_rules:
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/secrets/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000001
  - encrypted_regex: ^(data|stringData)$
    path_regex: management-clusters/demomc/organizations/demo-gitops/workload-clusters/demo0/mapi/.*\.enc\.yaml
    pgp: 0000000000000000000000000000000000000002
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
