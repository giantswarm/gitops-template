# secret-stores

`management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/secret-stores`

A `SecretStore` for every workload cluster of the organisation, made as the cluster comes up, so External Secrets
Operator can push secrets into it. Nobody writes a store per cluster: two Kyverno policies do it.

The organisation's namespace Kustomization, in `../../namespace.yaml`, applies this directory into `org-<name>`, as
`../../namespace/kustomization.yaml` lists it. It has no Flux Kustomization of its own.

## What's here

- `policy.yaml`: two Kyverno `NamespacedGeneratingPolicy`s that work as a pair, one hop each.
- `secret-store.yaml`: the store `default`, limited to the organisation's namespace, that the first hop reads the
  kubeconfig Secrets through.
- `kustomization.yaml`: lists the two.

## Why two hops

Cluster API writes a kubeconfig Secret for every cluster, `<cluster>-kubeconfig`, as soon as the cluster has an API
server. A `SecretStore` can't use it as it is: the store wants the client certificate, the key, the CA and the
server address as separate keys of a Secret. So the work is done in two hops:

1. `generate-eso-cluster-auth-from-kubeconfig` reacts to the kubeconfig Secret and generates an `ExternalSecret`,
   `<cluster>-eso-cluster-auth`. It reads the kubeconfig through `default`, takes it apart, and writes
   `tls.crt`, `tls.key`, `ca.crt` and `server` into a Secret of the same name. It refreshes every minute, so a renewed
   kubeconfig reaches the Secret too.
1. `generate-eso-cluster-store-from-cluster-auth` reacts to that Secret and generates the `SecretStore`
   `<cluster>-eso-cluster-store`, which signs in to the cluster with it.

The second hop has to wait for ESO to write the Secret, which is why it's a policy of its own rather than a second
object of the first. What you get is a store per cluster that exists from the moment the cluster does. Use it to push
Secrets into a cluster before anything else runs there, such as a registry token, a password, or another cluster's
kubeconfig for a tool that needs to reach it: see [`pushed-password`](../../workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-password/)
and [`pushed-kubeconfig`](../../workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-kubeconfig/). The
`<cluster>-eso-cluster-auth` Secret is also there for a tool that wants a cluster's credentials as separate keys
rather than as a kubeconfig.

When the kubeconfig Secret goes, with its cluster, so do the `ExternalSecret`, the Secret it wrote and the store.

## What Kyverno needs

They're `NamespacedGeneratingPolicy`s, not cluster-wide policies, so the organisation's `automation` ServiceAccount
can apply them. Kyverno accepts them whatever rights it has, but its background controller,
`kyverno/kyverno-background-controller`, does the generating and needs rights on the management cluster that you
can't grant yourself:

- in the organisation's namespace, to manage `ExternalSecret`s and `SecretStore`s and to read Secrets: the
  `ClusterRole` `write-kyverno-generated-externalsecrets`, bound by a `RoleBinding` of the same name;
- across the cluster, `list` on Secrets: Kyverno looks for the Secrets that trigger a namespaced policy in every
  namespace, and only then keeps the ones in the policy's own.

Check the first with `kubectl get clusterrole write-kyverno-generated-externalsecrets` and
`kubectl get rolebinding write-kyverno-generated-externalsecrets -n org-<name>`. `NotFound` means your management
cluster doesn't grant it: ask Giant Swarm. Without it no store appears at all, and the background controller's log,
`kubectl logs -n kyverno deployment/kyverno-background-controller`, says `forbidden`. Without the second, clusters
that exist before the policies get no store, new ones still do, and the log says `failed to list resources`.

The policies' `status` says `ready: false`, with "Policy is not ready for reporting, missing permissions", unless
Kyverno's reports controller may read Secrets across the cluster. That's about Kyverno's policy reports. The
policies generate all the same.

## When you copy it

Copy it with the organisation, unchanged. The generated stores read and write Secrets in the workload clusters'
`default` namespace, which every cluster has. To use another, change `remoteNamespace` in the second policy; the
namespace has to exist in every cluster, and the `org-*` namespaces exist only on the management cluster. For one
cluster, write a store of your own instead, see
[Push a cluster's kubeconfig to another cluster](/docs/how-to/workload-cluster-secrets.md#push-a-clusters-kubeconfig-to-another-cluster).

## Read more

- [Give every cluster a store with
  Kyverno](/docs/how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno)
