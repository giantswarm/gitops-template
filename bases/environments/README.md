# environments

`bases/environments`

Stages and regions, as kustomize Components. A cluster is in one region and, optionally, one stage, and it picks them
up by listing the Components in its `cluster/kustomization.yaml`:

```yaml
components:
  - ../../../../../../../bases/environments/regions/eu_central
  - ../../../../../../../bases/environments/stages/dev
```

Nothing applies this directory directly. The cluster's Flux `Kustomization` applies what the Components add, with the
cluster, into the organisation's namespace, `org-<name>`.

A Component, unlike a base, changes what the cluster already has: it adds a `valuesFrom` entry or replaces a version.
So a cluster can combine any region with any stage, and nobody has to keep a directory for every combination.

## What's here

- [`regions/`](regions/): where a cluster runs, such as `eu-central-1`, and an optional extra node pool there.
- [`stages/`](stages/): which versions a cluster runs, from dev through staging to prod.

## When you copy it

Rename and add regions and stages to match yours. Keep them as Components (`kind: Component`): a cluster lists them
under `components:`, never `resources:`. List the region before the stage, and both before the patch with the
cluster's own values, so the cluster's own values still win.

## Read more

- [Stages and regions tutorial](/docs/tutorials/intermediate/stages-and-regions.md)
- [Directories, branches or repositories](/docs/explanation/composition.md#directories-branches-or-repositories)
