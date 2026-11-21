# Put secrets into new workload clusters

Some secrets every workload cluster needs from the moment it exists, such as a registry token or a password for an
agent. External Secrets Operator (ESO) on the management cluster can put them into a new cluster for you:

- a secret you keep once in your secret manager, the same for every cluster;
- a password that an ESO generator makes for each cluster, so nobody writes it by hand.

ESO reaches the workload cluster through a `SecretStore` that points at the cluster's API server. You can keep that
store in Git for each cluster, or let a Kyverno `Policy` make one for every cluster as it appears. For the basics of
`ExternalSecret`s and stores, see [Read secrets from a secret manager](./external-secrets.md).

## Push secrets through a store in Git

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

The kind test runs this example, see [Workload cluster secrets](../reference/ci-checks.md#workload-cluster-secrets).

## Give every cluster a store with Kyverno

Rather than adding a store and its credentials to Git for each new cluster, let a Kyverno `Policy`, managed with GitOps
like everything else here, react to every new cluster and generate them from the kubeconfig Secret Cluster API writes
for it. The example in
[organizations/ORG_NAME/multicluster/secret-stores](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/secret-stores/)
has two files, both in the organisation's namespace, since customers on a Giant Swarm management cluster can't create
cluster-scoped objects:

- `policy.yaml`: the Kyverno `Policy` `generate-eso-cluster-auth-from-kubeconfig`, with two `generate` rules that chain:
    1. Every kubeconfig Secret Cluster API writes for a cluster gets an `ExternalSecret` that reads it through
       `default` and writes the client certificate and key, the cluster's CA and its API server into
       `<cluster>-eso-cluster-auth`, as `tls.crt`, `tls.key`, `ca.crt` and `server`. The rule matches the Secret by
       its type, `cluster.x-k8s.io/secret`, its `cluster.x-k8s.io/cluster-name` label and its name,
       `<cluster>-kubeconfig`, so the other Secrets Cluster API writes for the cluster, such as its CA or the
       `<cluster>-user-kubeconfig` of an EKS cluster, don't match.
    1. Every `<cluster>-eso-cluster-auth` Secret gets a `SecretStore` `<cluster>-eso-cluster-store` that reaches the
       workload cluster with them. It reads and writes Secrets in the workload cluster's `default` namespace: the
       `org-*` namespaces exist only on the management cluster. Change `remoteNamespace` to use another one that exists
       on every cluster.

    The rules name the namespace they generate in, `org-${organization}`, which Flux fills in, rather than templating it
    in Kyverno: for a templated namespace Kyverno checks the rights of the policy's author and of its own controllers
    across the whole cluster, which a customer can't grant. `generateExisting: true` covers the clusters that exist
    already, and `synchronize: true` deletes the generated objects again when the cluster's kubeconfig Secret goes.
    Deleting the policy, or its file from Git, which Flux then prunes, deletes every store and `ExternalSecret` it
    generated at once, and ESO deletes each `<cluster>-eso-cluster-auth` Secret with the `ExternalSecret` that owns it
    (`creationPolicy: Owner`): the apps' `ExternalSecret`s and `PushSecret`s that use the stores stop syncing until the
    policy is back, though the Secrets they already wrote stay.
- `secret-store.yaml`: the `SecretStore` `default` that the generated `ExternalSecret`s read the kubeconfig Secrets
  through. It reads the organisation's namespace as the `automation` ServiceAccount Giant Swarm's rbac-operator creates
  there.

Kyverno's background controller, the ServiceAccount `kyverno-background-controller` in `kyverno`, needs rights in the
organisation's namespace to manage the `ExternalSecret`s and `SecretStore`s the policy generates and to read the
kubeconfig Secrets that trigger it. Giant Swarm's rbac-operator grants them in every organisation's namespace, with the
ClusterRole `write-kyverno-generated-externalsecrets`, so the example doesn't. Without them, Kyverno rejects the policy.

The directory belongs with the organisation's other objects for several clusters, in `multicluster`, but has no
`Kustomization` of its own: the organisation's `namespace/kustomization.yaml` lists it as
`../multicluster/secret-stores`, and `multicluster/kustomization.yaml`, which the management cluster's `Kustomization`
applies, leaves it out. The organisation's namespace `Kustomization` puts the objects in the organisation's namespace
and fills in `${organization}`, in the namespace the policy generates in and in the one the `default` store reads, see
[The organisation's name](../reference/repo-structure.md#the-organisations-name). A cluster's apps then read from or
push to the cluster with `secretStoreRef: {kind: SecretStore, name: <cluster>-eso-cluster-store}` in the
organisation's namespace. For another organisation, copy the directory into its own `multicluster` and list it in its
`namespace/kustomization.yaml`.

The kind test checks the policy, see
[Workload cluster secret stores](../reference/ci-checks.md#workload-cluster-secret-stores).

## Push a generated password

The `out-of-band-no-flux` cluster's apps have an example that uses its generated store:
[apps/pushed-password/pushed-password.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-password/pushed-password.yaml).
External Secrets Operator's `Password` generator makes a password, so no value is kept in Git, and a `PushSecret` in
`org-${organization}` writes it through `${cluster_name}-eso-cluster-store` into the Secret `pushed-password`, key
`password`, in the workload cluster's `default` namespace. `updatePolicy: IfNotExists` keeps the first password there,
though the generator makes a new one at every refresh. The cluster's apps Kustomization applies the example once the
cluster is ready; if Kyverno and ESO haven't made the store yet, ESO retries the `PushSecret` until they have. The same
cluster also pushes Secrets through a store of its own in Git, which needs no Kyverno, see
[Push secrets through a store in Git](#push-secrets-through-a-store-in-git).

To push a Secret into another cluster, copy the file into that cluster's `apps/` directory and list it in its
`apps/kustomization.yaml`: `${cluster_name}` and `${organization}` come from the cluster's apps Kustomization, so the
store name follows the cluster. To push a Secret you already have instead of a generated one, replace the
`selector.generatorRef` with `selector.secret.name`, remove the `Password`, and use `updatePolicy: Replace`, ESO's
default, so that a change to the Secret, such as a rotation, reaches the workload cluster.

## Use your secret manager

The example in `common-secret.yaml` reads the [store for testing](./external-secrets.md#a-secret-store-for-testing).
Point its `ExternalSecret` at a store for your secret manager instead, in the organisation's namespace, as
[Create a SecretStore for your secret manager](./external-secrets.md#create-a-secretstore-for-your-secret-manager)
describes. A `SecretStore` only serves the `ExternalSecret`s in its own namespace, so `common-secret.yaml`, in
`org-ORG_NAME`, needs the store in `org-ORG_NAME`:

```yaml
spec:
  secretStoreRef:
    kind: SecretStore
    name: azure-key-vault  # or aws-secrets-manager
```

Name the secret in your secret manager `workload-clusters-common-token`, or change `remoteRef.key` to its name.
Azure Key Vault allows only letters, digits and hyphens in names.
