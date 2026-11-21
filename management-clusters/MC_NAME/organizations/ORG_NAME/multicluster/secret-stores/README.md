# secret-stores

`management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/secret-stores`

A `SecretStore` for every workload cluster of the organisation, made as the cluster comes up, so External Secrets
Operator can push secrets into it. Nobody writes a store per cluster: a Kyverno policy does it.

The organisation's namespace Kustomization, in `../../namespace.yaml`, applies this directory into `org-<name>`, as
`../../namespace/kustomization.yaml` lists it. It has no Flux Kustomization of its own.

## What's here

- `policy.yaml`: a Kyverno `Policy`. When Cluster API writes a cluster's kubeconfig Secret, it generates an
  `ExternalSecret` that turns the kubeconfig into the credentials in `<cluster>-eso-cluster-auth`, and from those a
  `SecretStore`, `<cluster>-eso-cluster-store`, that reaches the cluster. When the kubeconfig Secret goes, so do they.
- `secret-store.yaml`: the store `default` that those `ExternalSecret`s read the kubeconfig Secrets through, limited
  to the organisation's namespace.
- `kustomization.yaml`: lists the two.

It's a namespaced `Policy`, not a `ClusterPolicy`, so the organisation's `automation` ServiceAccount can apply it.
Kyverno needs rights in the namespace to act on it, which rbac-operator grants on a Giant Swarm management cluster.

## When you copy it

Copy it with the organisation, unchanged. Change `remoteNamespace` in the generated store if you want to push into
another namespace than `default` in the workload clusters; the namespace has to exist there. Keep
`generate.namespace` as `org-${organization}`: Kyverno checks a templated namespace across the whole cluster.

## Read more

- [Give every cluster a store with
  Kyverno](/docs/how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno)
