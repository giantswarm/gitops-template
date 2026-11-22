# pushed-kubeconfig

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-kubeconfig`

This cluster's kubeconfig, pushed into another cluster, for a tool there that needs to reach this one. The store it
goes through, `tools-cluster-eso-cluster-store`, is the one the Kyverno policies in the organisation's
`multicluster/secret-stores/` make for the other cluster, `tools-cluster`, as soon as that cluster's kubeconfig exists.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies it into `org-<name>` once the
cluster is up. Until Kyverno and ESO have made the store, ESO retries the push.

## What's here

- `pushed-kubeconfig.yaml`: a `PushSecret` that copies this cluster's kubeconfig Secret, `${cluster_name}-kubeconfig`,
  into a Secret of the same name, key `value`, in the other cluster's `default` namespace, and again within the hour
  when Cluster API renews it.

The kubeconfig signs in as cluster-admin of this cluster. Whoever may read Secrets in that namespace of the other
cluster can do anything here.

## When you copy it

Change `tools-cluster` in the store's name to the cluster that runs the tool. The store writes into `default`; that
namespace, or the one you point a store at instead, has to exist in the other cluster. Deleting the `PushSecret`
leaves the copy where it is: delete it there yourself. It needs the organisation's `multicluster/secret-stores/`, so
keep that too.

## Read more

- [Push a cluster's kubeconfig to another cluster](/docs/how-to/workload-cluster-secrets.md#push-a-clusters-kubeconfig-to-another-cluster)
