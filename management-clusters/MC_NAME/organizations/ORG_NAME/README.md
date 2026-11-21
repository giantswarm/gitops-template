# management-clusters/MC_NAME/organizations/ORG_NAME

The example organisation: its `Organization`, the Flux Kustomizations that fill its namespace, and its workload
clusters. Copy it once per organisation.

The management cluster's Kustomization, in `MC_NAME.yaml`, applies this directory through `kustomization.yaml`, but
only the objects that don't live in the organisation's namespace: the `Organization` itself and two Flux
Kustomizations in `default`. organization-operator creates the namespace, `org-<name>`, for the `Organization`, and
the namespace Kustomization in `namespace.yaml` then applies everything that goes into it.

## What's here

- `ORG_NAME.yaml`: the `Organization`. Its `metadata.name` is the organisation's name, and the only place you set it.
  Deleting it deletes the namespace and every cluster in it, so it has `kustomize.toolkit.fluxcd.io/prune: disabled`
  and `giantswarm.io/prevent-deletion: "true"`.
- `namespace.yaml`: the organisation's namespace Kustomization, which applies [`namespace/`](namespace/) into
  `org-<name>`.
- `kustomization.yaml`: lists `ORG_NAME.yaml`, `namespace.yaml` and `multicluster/`, and holds the replacements that
  copy the organisation's name from the `Organization` into the Flux Kustomizations, as `${organization}` and as the
  namespace Kustomization's `targetNamespace`.
- [`namespace/`](namespace/): everything the organisation keeps in its namespace.
- [`multicluster/`](multicluster/): apps that roll out to several of the organisation's clusters, and the clusters'
  secret stores.
- [`workload-clusters/`](workload-clusters/): one directory per workload cluster, and their Flux Kustomizations.

## When you copy it

Rename the directory, set the organisation's name in `ORG_NAME.yaml`, and change the `TODO` names in `namespace.yaml`
and `multicluster/apps.yaml`. Leave `org-ORG_NAME` and `organization: "ORG_NAME"` as they are: the replacements fill
them in. If you don't use the replacements, `kustomization.yaml` lists the files you'd have to edit by hand. A
SOPS-encrypted Secret in `namespace/` must name the real namespace, `org-<name>`, as changing an encrypted file breaks
it.

## Read more

- [2. Add an organisation](/docs/tutorials/basic/getting-started.md#2-add-an-organisation)
- [Flux Kustomizations](/docs/reference/repo-structure.md#flux-kustomizations)
