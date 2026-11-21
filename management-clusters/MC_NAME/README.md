# management-clusters/MC_NAME

The example management cluster. Copy it once per management cluster, and rename it to that cluster's name.

The management cluster's Flux Kustomization, `mc-name-gitops` in `MC_NAME.yaml`, applies this directory. What it
creates is in the `default` namespace, apart from the Organizations, which have none. It applies itself too, so a
change to it in Git takes effect; you apply it by hand once, when you connect the management cluster. It decrypts
with the master key, the `sops-gpg-master` Secret. There's no `kustomization.yaml` here, so Flux takes every YAML file
in this directory and below it, and builds a directory that has a `kustomization.yaml` the way that file says.

## What's here

- `MC_NAME.yaml`: the management cluster's Flux Kustomization.
- [`.sops.keys/`](.sops.keys/): the public SOPS keys.
- [`secrets/`](secrets/): the master key, encrypted with itself.
- [`notifications/`](notifications/): commit statuses on GitHub for the Kustomizations in `default`.
- [`organizations/`](organizations/): one directory per organisation.

## When you copy it

Rename the directory and change the `TODO`s in `MC_NAME.yaml`: the Kustomization's name, `spec.path` and the
`GitRepository` it reads. Give the new cluster its own master key, not a copy of another cluster's. Keep
`prune: true`: the objects whose deletion would delete a cluster are protected one by one instead.

## Read more

- [1. Connect the management cluster](/docs/tutorials/basic/getting-started.md#1-connect-the-management-cluster)
- [Flux Kustomizations](/docs/reference/repo-structure.md#flux-kustomizations)
- [From a commit to a cluster](/docs/explanation/how-it-works.md#from-a-commit-to-a-cluster)
