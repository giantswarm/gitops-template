# ORG_NAME/multicluster

What the organisation rolls out to several of its workload clusters at once, rather than cluster by cluster: apps, and
the secret store every cluster gets.

Two Kustomizations share this directory. The management cluster's Kustomization applies `kustomization.yaml` here,
which holds only the Flux Kustomization in `apps.yaml`, in `default`. That one applies [`apps/`](apps/). The
organisation's namespace Kustomization applies [`secret-stores/`](secret-stores/) into `org-<name>`, as
`namespace/kustomization.yaml` lists it.

## What's here

- `apps.yaml`: the Flux Kustomization that applies `apps/`.
- `kustomization.yaml`: lists `apps.yaml`, and leaves the two directories to their own Kustomizations.
- [`apps/`](apps/): apps on several clusters, one `ResourceSet` each.
- [`secret-stores/`](secret-stores/): a Kyverno policy that gives each workload cluster a `SecretStore`.

## When you copy it

Change the `TODO` name in `apps.yaml` to your management cluster and organisation. Leave `organization: "ORG_NAME"`
as it is: the organisation's `kustomization.yaml` fills it in. Delete `secret-stores/`, and its line in
`../namespace/kustomization.yaml`, if you don't push secrets into your clusters with ESO.

## Read more

- [Multicluster apps tutorial](/docs/tutorials/advanced/multicluster-apps.md#the-multicluster-directory)
