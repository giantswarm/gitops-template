# Secrets

Clusters and apps need secrets: the token Flux reads the repository with, an app's passwords, a registry pull secret.
A GitOps repository holds everything else, but a secret can't sit in Git in plain text. This template shows two ways to
handle them, and they aren't rivals:

- **SOPS** keeps a secret in the repository, encrypted. Flux decrypts it when it applies it.
- **External Secrets Operator (ESO)** keeps a secret in a secret manager, such as Vault, AWS Secrets Manager or Azure
  Key Vault. The repository holds only an `ExternalSecret` that says which secret goes where, and ESO copies the value
  into a Kubernetes Secret.

You can use SOPS only, ESO only, or both. Nothing in the template needs both. The examples show both side by side,
each delivering Secrets of its own, so you can pick per secret. What you pick is a route for each Secret, not a
second copy of it: see [One Secret, one route](#one-secret-one-route).

The [basic tutorial](../tutorials/basic/getting-started.md) uses both: SOPS for the secrets Flux needs to start, and
ESO for the app's. That's the combination this page recommends when you have a secret manager, and the rest of the
page explains why.

## One Secret, one route

> [!Caution]
> Each Secret comes from SOPS or from ESO, never from both. kustomize-controller applies the SOPS Secret and ESO
> writes its own over it, each overwrites the other, the Secret flaps, and whichever wrote last wins. See
> [One owner per object](./one-owner.md#flux-and-external-secrets-operator).

Where the docs show one Secret both ways, such as an app's `-user-secrets` or the commit status token, they show two
routes to the same Secret: the same name, namespace, type, keys and labels, and values of the same shape. You apply
one of them. Where you use both tools, an app's Secret comes from ESO, and the SOPS copy is the alternative for a
cluster without a secret manager.

If an app needs a value that only the other tool has, don't give its Secret a second deliverer. Put the value in the
same source, your secret manager or the encrypted file, or in a second Secret with its own name and its own entry in
the app's `valuesFrom`. helm-controller merges the entries in order, so the second Secret's values win over the first's
where both set a key, see [App values](../reference/values.md#app-values). An app from an App Template gets the entry
with a patch of its `HelmRelease`.

## Bootstrap secrets with SOPS

Some secrets have to exist before Flux can apply anything. Flux reads the repository with a token, and decrypts the
repository's other secrets with a key: neither can come from the repository through Flux, as Flux would need them to
read it. You create them by hand once, when you connect the management cluster, and from then on the repository keeps
them, so that Flux puts them back if they change and a new management cluster gets them from Git.

With SOPS, each management cluster has a master key, a GPG key pair. Its public key is in the repository, so anyone
can encrypt for it, and its private key is in the `sops-gpg-master` Secret on the management cluster, where Flux
decrypts with it. Anyone who can read Secrets in `default` can decrypt too, see [Risks](#risks). Flux's repository
token goes in the management cluster's `secrets` directory, encrypted with the master key. The private keys of the
workload clusters go in their organisation's `namespace/secrets`, encrypted with the master key too, so each cluster
can have a key of its own.
[SOPS keys](../reference/sops-keys.md) lists the keys and what each one decrypts.

SOPS needs nothing outside the repository and the management cluster. That suits the secrets a secret manager can't
give you yet, because nothing is running to read it, and the ones you want to come back exactly as they were when you
rebuild a management cluster from Git.

The steps are in [Keep secrets in the repository](../how-to/sops.md).

## App secrets with ESO

An app's secrets change more often, belong to more people, and often exist in a secret manager already: a database
password, an API key, a certificate. Copying them into Git, even encrypted, makes a second copy to rotate and to keep
in step. With ESO, the secret stays where it is:

1. A `SecretStore` in the organisation's namespace says how to reach the secret manager. With workload identity, as the
   bases in [bases/secret_stores](/bases/secret_stores/) use, it stores no credential at all.
1. An `ExternalSecret` next to the app says which secret to read and which Kubernetes Secret to write it into, such as
   the app's `-user-secrets`, which its `HelmRelease` reads.
1. ESO refreshes the Secret every `refreshInterval`, and Flux upgrades the app as soon as the Secret changes.

ESO runs on every Giant Swarm management cluster, so there's nothing to install. It can also make secrets, such as
passwords, and push secrets into new workload clusters, see
[Put secrets into new workload clusters](../how-to/workload-cluster-secrets.md).

The steps are in [Read secrets from a secret manager](../how-to/external-secrets.md).

### Four kinds of secret store

"Secret store" means four different things in these docs, and each has its own place:

| Store | What it is | Where it lives |
| --- | --- | --- |
| Your secret manager's store | a `SecretStore` that reads your secret manager, such as one from [bases/secret_stores](/bases/secret_stores/). The apps' `ExternalSecret`s read it | the organisation's `namespace/secret-stores`, applied into the organisation's namespace. If Flux's own secrets come from your secret manager too, a second one in `default`, in the management cluster's directory |
| The store named `default` | a `SecretStore` with ESO's `kubernetes` provider, which reads Secrets in the organisation's own namespace, such as the workload clusters' kubeconfigs | the organisation's `multicluster/secret-stores`, next to the Kyverno policy whose `ExternalSecret`s read through it |
| The generated per-cluster store | `<cluster>-eso-cluster-store`, which the Kyverno policy makes for each workload cluster as it comes up, so that ESO can push secrets into the cluster | nowhere in the repository: Kyverno writes it into the organisation's namespace |
| The test store | `gitops-test`, with ESO's fake provider, which keeps dummy values in the store itself, so you can try the docs without a secret manager | applied by hand, see [A secret store for testing](../how-to/external-secrets.md#a-secret-store-for-testing), or in `namespace/secret-stores` while you follow the [basic tutorial](../tutorials/basic/getting-started.md#2-add-an-organisation) |

A `SecretStore` is a custom resource, not a Secret, so everyone with read access to the management cluster can read
what's in one, in any namespace. That's why the first three hold no credential themselves, and why the test store
holds dummy values and never a real secret.

## Which secret goes where

| Secret | SOPS | ESO | Recommended |
| --- | --- | --- | --- |
| The master key, `sops-gpg-master` | the only place for it, if you use SOPS | no | SOPS, created by hand once |
| Flux's repository token, `github-https-credentials` | encrypted in `MC_NAME/secrets` | an `ExternalSecret` in `default` | SOPS: Flux needs it before anything else runs |
| A workload cluster's SOPS key | encrypted with the master key in the organisation's `namespace/secrets` | no | SOPS, if the cluster has SOPS-encrypted files |
| A `SecretStore`'s credential | encrypted next to the store | no: ESO needs it to read anything | none: use workload identity, so there's no credential |
| An app's secret values, `-user-secrets` | `secret.enc.yaml`, encrypted with the cluster's key | an `ExternalSecret` | ESO, if you have a secret manager |
| A registry pull secret | `pullsecret.enc.yaml`, encrypted with the cluster's key | an `ExternalSecret` | either: the one you use for the app's values |
| The commit status token | encrypted in each `notifications` directory | an `ExternalSecret` in each | either |
| A secret every workload cluster needs | no | an `ExternalSecret` and a `PushSecret` | ESO |
| A generated password | no | a generator, such as `Password` | ESO |

Without a secret manager, SOPS covers every row that has a SOPS column, which is all of them but the last two. With a
secret manager and no wish to keep keys, ESO covers everything but the master key and the cluster keys, which you then
don't need: create Flux's repository token from your secret manager, see
[Keep the repository token in your secret manager](../how-to/external-secrets.md#keep-the-repository-token-in-your-secret-manager),
and leave the SOPS directories out.

## Risks

Neither way is free of risk. They put the risk in different places.

With SOPS, the danger is the private keys:

- Flux needs each private key without a passphrase, in a Secret on the management cluster. Anyone who can read that
  Secret can decrypt every file encrypted for it. Limit who can read Secrets in `default` and the `org-*` namespaces.
- You keep a copy of each private key outside the cluster, to change the encrypted files later. That copy is the one
  most likely to leak: keep it in a password manager, see
  [Keep a private key in a password manager](../how-to/sops.md#keep-a-private-key-in-a-password-manager), and delete it
  from your keyring when you're done.
- Git keeps history. If a key leaks, re-encrypting the files with a new key doesn't protect the old commits, which an
  attacker with the old key can still read. Change the secrets themselves too, not only the key.
- Deleting a key Secret stops Flux for every cluster that uses it, so the template protects them, see
  [Deletion protection](./deletion-protection.md).

With ESO, the danger is the dependency:

- Your apps depend on the secret manager and on ESO. If either is down, Secrets don't refresh; the ones already
  written stay, so running apps keep working, but a new cluster or a new app waits.
- The `SecretStore` can read whatever its identity can read. Give each organisation's store an identity that reads only
  that organisation's secrets.
- A Secret ESO wrote is a plain Kubernetes Secret, readable by anyone who can read Secrets in its namespace, the same
  as a decrypted SOPS Secret.

Giant Swarm's [External Secrets Operator](https://docs.giantswarm.io/overview/security/external-secrets-operator/)
docs describe the risks of depending on it in more detail. [SOPS keys](../reference/sops-keys.md#security) covers the
cryptography of the keys.
