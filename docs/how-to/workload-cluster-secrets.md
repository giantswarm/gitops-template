# Put secrets into new workload clusters

Every workload cluster needs some secrets from the moment it exists, such as a registry token or a password for an
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

The cluster's apps Flux `Kustomization`, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies the directory once the
cluster is ready, so the secrets arrive as soon as the cluster can take them. The `PushSecret`s copy them again every
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
    1. Every kubeconfig Secret Cluster API writes for a cluster gets an `ExternalSecret` that reads exactly that Secret
       through `default` and writes the client certificate and key, the cluster's CA and its API server into
       `<cluster>-eso-cluster-auth`, as `tls.crt`, `tls.key`, `ca.crt` and `server`. The rule matches the Secret by
       its type, `cluster.x-k8s.io/secret`, its `cluster.x-k8s.io/cluster-name` label and its name,
       `<cluster>-kubeconfig`, so the other Secrets Cluster API writes for the cluster, such as its CA or the
       `<cluster>-user-kubeconfig` of an EKS cluster, don't match.
    1. Every `<cluster>-eso-cluster-auth` Secret that ESO writes, which it labels
       `reconcile.external-secrets.io/managed: "true"`, gets a `SecretStore` `<cluster>-eso-cluster-store` that reaches
       the workload cluster with them. It reads and writes Secrets in the workload cluster's `default` namespace: the
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

### Why two hops

A `SecretStore` can't sign in with a kubeconfig Secret as Cluster API writes it: it wants the certificate, the key,
the CA and the server as separate keys. The first hop takes the kubeconfig apart into `<cluster>-eso-cluster-auth`,
refreshing every minute so a renewed kubeconfig follows. The second hop can only start once ESO has written that
Secret, so it's a rule of its own, triggered by the Secret, and builds the store from it.

The store is what you came for: one per cluster, there from the moment the cluster has a kubeconfig, which is the
moment you can first push a Secret into it. Use it for what a cluster needs before anything else runs there, as
[Push a generated password](#push-a-generated-password) and
[Push a cluster's kubeconfig to another cluster](#push-a-clusters-kubeconfig-to-another-cluster) do. The
`<cluster>-eso-cluster-auth` Secret is useful on its own too, for a tool that wants a cluster's credentials as
separate keys.

### What Kyverno needs

Kyverno's background controller, the ServiceAccount `kyverno-background-controller` in `kyverno`, does the
generating. It needs rights in the organisation's namespace to manage the `ExternalSecret`s and `SecretStore`s the
policy generates and to read the kubeconfig Secrets that trigger it. The example can't ship them and you can't grant
them yourself: on a Giant Swarm management cluster, rbac-operator grants them with the `ClusterRole`
`write-kyverno-generated-externalsecrets`, bound in every `org-*` namespace by a `RoleBinding` of the same name.

Kyverno checks those rights when the policy is applied, and refuses the policy without them: Flux then reports the
organisation's namespace `Kustomization` as failed, with Kyverno's refusal in its message. Check the rights:

```sh
kubectl get clusterrole write-kyverno-generated-externalsecrets
kubectl get rolebinding write-kyverno-generated-externalsecrets -n org-<name>
```

If either says `NotFound`, your management cluster doesn't grant them yet: that's Giant Swarm's to do, so ask.

### Where it lives

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
though the generator makes a new one at every refresh. The cluster's apps `Kustomization` applies the example once the
cluster is ready; if Kyverno and ESO haven't made the store yet, ESO retries the `PushSecret` until they have. The same
cluster also pushes Secrets through a store of its own in Git, which needs no Kyverno, see
[Push secrets through a store in Git](#push-secrets-through-a-store-in-git).

To push a Secret into another cluster, copy the file into that cluster's `apps/` directory and list it in its
`apps/kustomization.yaml`: `${cluster_name}` and `${organization}` come from the cluster's apps `Kustomization`, so the
store name follows the cluster. To push a Secret you already have instead of a generated one, replace the
`selector.generatorRef` with `selector.secret.name`, remove the `Password`, and use `updatePolicy: Replace`, ESO's
default, so that a change to the Secret, such as a rotation, reaches the workload cluster.

## Push a cluster's kubeconfig to another cluster

Some tools run in one cluster and reach into others: something that deploys to the whole fleet, say, or watches it.
The tool needs a kubeconfig for every cluster it reaches, and the management cluster has one for each, written by
Cluster API. The example pushes the `out-of-band-no-flux` cluster's kubeconfig into the cluster that runs the tool:
[apps/pushed-kubeconfig/pushed-kubeconfig.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-kubeconfig/pushed-kubeconfig.yaml).

A `PushSecret` in `org-${organization}` copies `${cluster_name}-kubeconfig`, key `value`, through
`tools-cluster-eso-cluster-store`, the store the policy generates for the cluster `tools-cluster`, into a Secret of
the same name in that cluster's `default` namespace. `updatePolicy: Replace`, ESO's default, writes a renewed
kubeconfig over the copy at the next refresh, within the hour. Change `tools-cluster` to the cluster that runs your
tool. Each cluster whose kubeconfig the tool needs gets the file in its own `apps/`, and they all push to the same
store.

The kubeconfig signs in as cluster-admin of the cluster it's for. Whoever may read Secrets in the namespace you push
it into can do anything in that cluster, so push it into a namespace only the tool reads. If the tool wants the
certificate, key, CA and server as separate keys, push `${cluster_name}-eso-cluster-auth` instead, which the
policy's first rule writes in that shape.

The namespace a store writes into has to exist in the target cluster: ESO doesn't create it, and the `PushSecret`
fails until someone does. The generated store writes into `default`, which every cluster has. To push into the tool's
own namespace instead, give that one cluster a store of your own next to the `PushSecret`, the way
[apps/workload-cluster-secrets/secret-store.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets/secret-store.yaml)
does, with the namespace in `remoteNamespace`:

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: tools-cluster-fleet-access
  namespace: org-${organization}
spec:
  provider:
    kubernetes:
      authRef:
        name: tools-cluster-kubeconfig
        key: value
      # has to exist in tools-cluster before the PushSecret can write there
      remoteNamespace: fleet-access
```

Then point the `PushSecret`'s `secretStoreRefs` at `tools-cluster-fleet-access`. Deleting the `PushSecret` leaves the
copy in the other cluster, as ESO's default `deletionPolicy: None` does: delete it there yourself when the tool no
longer needs it.

The kind test runs the example, with the vCluster standing in for both clusters, see
[Workload cluster secret stores](../reference/ci-checks.md#workload-cluster-secret-stores).

## Use your secret manager

The example in `common-secret.yaml` reads the [store for testing](./external-secrets.md#a-secret-store-for-testing).
Point its `ExternalSecret` at a store for your secret manager instead, in the organisation's namespace, as
[Create a `SecretStore` for your secret manager](./external-secrets.md#create-a-secretstore-for-your-secret-manager)
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
