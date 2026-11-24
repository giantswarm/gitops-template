# secret_stores

`bases/secret_stores`

External Secrets Operator `SecretStore`s for cloud secret managers that keep no credential anywhere. Each one signs in
with a token Kubernetes issues for a ServiceAccount, so there's no access key in the cluster or in Git to leak or
rotate. That needs a cloud's workload identity, which AWS and Azure have. On vSphere and Cloud Director, see
[Secret stores](/docs/how-to/other-providers.md#secret-stores).

Nothing applies this directory directly. The bases have no namespace: a `kustomization.yaml` in your organisation's
`namespace/` lists one, and the Flux `Kustomization` for the organisation's namespace, `namespace.yaml`, applies it into
the organisation's namespace, `org-<name>`, next to the `ExternalSecret`s that read through it. A `SecretStore` only
serves `ExternalSecret`s in its own namespace.

These are for ESO. You can use ESO, SOPS or both: SOPS keeps secrets encrypted in Git, ESO reads them from a secret
manager, and neither needs the other.

## What's here

- [`aws-secrets-manager/`](aws-secrets-manager/): AWS Secrets Manager, with IAM roles for service accounts.
- [`azure-key-vault/`](azure-key-vault/): Azure Key Vault, with Azure Workload Identity.

Each has a `secret-store.yaml`, a `service-account.yaml` and a `kustomization.yaml` that lists both. The cloud side
differs, so each has its own README.

## When you copy it

Use the base for your secret manager as it is, and set the values marked `TODO` there. Don't add a credential to a
store here: that's what these bases avoid.

## Read more

- [Create a SecretStore](/docs/how-to/external-secrets.md#create-a-secretstore-for-your-secret-manager)
- [SOPS and ESO in one repository](/docs/explanation/secrets.md)
