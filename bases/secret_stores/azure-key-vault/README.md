# bases/secret_stores/azure-key-vault

A `SecretStore` named `azure-key-vault` that reads Azure Key Vault with Azure Workload Identity. ESO signs in as the
managed identity the ServiceAccount names, with a token Kubernetes issues for that ServiceAccount, so no client secret
is stored anywhere.

Nothing applies this directory directly. A `kustomization.yaml` in your organisation's `namespace/` lists it, and the
organisation's namespace Kustomization applies it into `org-<name>`.

## What's here

- `secret-store.yaml`: the `SecretStore`, with the URL of your key vault.
- `service-account.yaml`: the ServiceAccount `external-secrets-azure-key-vault`, annotated with the managed identity's
  client ID and your tenant ID.
- `kustomization.yaml`: lists both.

## When you copy it

You don't copy it, you list it. Set the key vault's URL in `secret-store.yaml`, and the client ID and tenant ID in
`service-account.yaml`. In Azure, create a managed identity that can read the key vault's secrets, and give it a
federated credential for the management cluster's service account issuer, the subject
`system:serviceaccount:org-<name>:external-secrets-azure-key-vault` and the audience `api://AzureADTokenExchange`.
Giant Swarm support can give you the issuer URL. Keep the ServiceAccount's name, or change the subject to match. Key
Vault allows only letters, digits and hyphens in secret names.

## Read more

- [Create a SecretStore](/docs/how-to/external-secrets.md#create-a-secretstore-for-your-secret-manager)
- [Use your secret manager](/docs/how-to/workload-cluster-secrets.md#use-your-secret-manager)
