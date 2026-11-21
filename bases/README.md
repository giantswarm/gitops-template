# bases

The building blocks that clusters and organisations share. Write something here once, and every cluster that lists
it gets it; change it here, and they all get the change.

Nothing applies this directory. A base only reaches a cluster when a `kustomization.yaml` under `management-clusters/`
lists it by relative path: under `resources:` for a base, under `components:` for a stage or region. For example, a
cluster's `cluster/kustomization.yaml` has:

```yaml
resources:
  - ../../../../../../../bases/clusters/capa
components:
  - ../../../../../../../bases/environments/regions/eu_central
```

The variables in a base, such as `${cluster_name}` and `${organization}`, are filled in by the Flux Kustomization
that applies the cluster's directory.

## What's here

- [`apps/`](apps/): App Templates, one app's configuration to reuse across clusters.
- [`clusters/`](clusters/): cluster bases, one per provider.
- [`environments/`](environments/): stages and regions, as kustomize Components.
- [`secret_stores/`](secret_stores/): External Secrets Operator stores that keep no credentials.
- [`shared_objects/`](shared_objects/): objects every organisation gets a copy of.
- [`stacks/`](stacks/): several apps installed together.

## When you copy it

Keep the directory where it is: the relative paths in `management-clusters/` point here. Add your own bases next to
these. A base names no particular cluster or organisation: it writes `${cluster_name}` and `${organization}` instead,
or it stops being reusable.

## Read more

- [Bases, Components and stacks](/docs/explanation/composition.md#bases-components-and-stacks)
- [Bases and variables](/docs/explanation/how-it-works.md#bases-and-variables)
