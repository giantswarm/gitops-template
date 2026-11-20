# Push secrets into a new Workload Cluster

Some secrets every workload cluster needs from the moment it exists, such as a registry token or a password for an
agent. This guide shows how External Secrets Operator (ESO) on the management cluster puts them into a new cluster:

- a secret you keep once in your secret manager, the same for every cluster;
- a password that an ESO generator makes for each cluster, so nobody writes it by hand.

ESO runs on every Giant Swarm management cluster. For the basics of `ExternalSecret` and stores, see
[Getting started](../getting-started.md).

## How it works

The example is in the out-of-band-no-flux cluster, in
[apps/workload-cluster-secrets](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets/):

- [secret-store.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets/secret-store.yaml)
  is a `SecretStore` with the `kubernetes` provider that points at the workload cluster. It signs in with the
  `${cluster_name}-kubeconfig` Secret the management cluster has for every cluster, and writes into the `default`
  namespace, which every new cluster has.
- [common-secret.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets/common-secret.yaml)
  has an `ExternalSecret` that reads `workload-clusters-common-token` from your secret manager into the
  `${cluster_name}-common-secret` Secret on the management cluster, and a `PushSecret` that copies it into the
  workload cluster as the `common-secret` Secret.
- [generated-password.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets/generated-password.yaml)
  has a [`Password` generator](https://external-secrets.io/latest/api/generator/password/), an `ExternalSecret` that
  writes its password into `${cluster_name}-generated-password`, and a `PushSecret` that copies it into the workload
  cluster as `generated-password`. The `ExternalSecret` has `refreshPolicy: CreatedOnce`: without it, ESO makes a new
  password at every refresh. The `PushSecret` has `updatePolicy: IfNotExists`, so it writes the password only into a
  cluster that hasn't got one: if the Secret on the management cluster is ever made again, with a new password, the
  workload cluster keeps the one it has.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies the directory once the cluster
is ready, so the secrets arrive as soon as the cluster can take them. The `PushSecret`s copy them again every
`refreshInterval`, so a secret you change in your secret manager reaches the cluster within two hours, one refresh of
each.

To push a secret into another cluster, copy the directory into that cluster's `apps` and add its files to
`apps/kustomization.yaml`. For other secrets, add an `ExternalSecret` and a `PushSecret` the same way. ESO has other
generators too, for example `ECRAuthorizationToken` and `ACRAccessToken` for short-lived registry tokens, see
[Generators](https://external-secrets.io/latest/api/generator/).

The `PushSecret`s keep the default `deletionPolicy: None`: deleting them leaves the Secrets in the workload cluster.

## Use your secret manager

The example reads the test store of [Secret store for testing](../appendices.md#secret-store-for-testing). Point the
`ExternalSecret` in `common-secret.yaml` at a store for your secret manager instead. The bases in
[bases/secret_stores](/bases/secret_stores/) give one for each of these, both signing in with a token that Kubernetes
issues for a ServiceAccount, so no cloud credential is stored in the cluster or the repository:

- [azure-key-vault](/bases/secret_stores/azure-key-vault/) reads Azure Key Vault with Azure Workload Identity. In
  Azure, create a managed identity that can read the key vault's secrets, and give it a federated credential for the
  management cluster's service account issuer and the subject
  `system:serviceaccount:org-ORG_NAME:external-secrets-azure-key-vault`, with the audience
  `api://AzureADTokenExchange`, which ESO asks for. Set the key vault's URL in `secret-store.yaml`, and the identity's
  client ID and your tenant ID in `service-account.yaml`.
- [aws-secrets-manager](/bases/secret_stores/aws-secrets-manager/) reads AWS Secrets Manager with IAM roles for
  service accounts. In AWS, create an IAM role that can read your secrets and that trusts the management cluster's
  service account issuer for the subject `system:serviceaccount:org-ORG_NAME:external-secrets-aws-secrets-manager`
  and the audience `sts.amazonaws.com`, which ESO asks for.
  Set the region in `secret-store.yaml` and the role's ARN in `service-account.yaml`.

Ask Giant Swarm support for your management cluster's service account issuer URL.

The bases have no namespace. Use one in your organisation's directory, so the store is in the organisation's
namespace next to the clusters' `ExternalSecret`s, for example in
`management-clusters/MC_NAME/organizations/ORG_NAME/secret-stores/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: org-ORG_NAME
resources:
  - ../../../../../bases/secret_stores/azure-key-vault
```

Keep the placeholder namespace `org-ORG_NAME` and add `secret-stores` to the `resources` of the organisation's
`kustomization.yaml`: `MC_NAME.yaml` then applies it with the rest of the organisation, and the organisation's
replacements put its name in place of the placeholder, see
[The organisation's name](../reference/repo-structure.md#the-organisations-name). A `SecretStore` only serves the
`ExternalSecret`s in its own namespace, so `common-secret.yaml`, in `org-ORG_NAME`, needs this store in
`org-ORG_NAME`. For the store in
`default` that [Getting started](../getting-started.md) also reads, use the base the same way with
`namespace: default`, and add that namespace's subject to the managed identity's federated credentials or the IAM
role's trust policy: `system:serviceaccount:default:external-secrets-azure-key-vault` or
`system:serviceaccount:default:external-secrets-aws-secrets-manager`. Then point the `ExternalSecret` at the store:

```yaml
spec:
  secretStoreRef:
    kind: SecretStore
    name: azure-key-vault  # or aws-secrets-manager
```

Name the secret in your secret manager `workload-clusters-common-token`, or change `remoteRef.key` to its name.
Azure Key Vault allows only letters, digits and hyphens in names.

## How it's tested

The kind test runs the example for real: it creates the test store, and a vCluster stands in for the workload
cluster. It checks that both Secrets are on the management cluster and in the workload cluster. CI can't reach a
cloud secret manager, so `tools/test-all-ff validate` only builds each base in `bases/secret_stores` and checks it
against the schemas of its kinds.
