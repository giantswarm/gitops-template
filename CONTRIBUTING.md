# Contributing

## Bumping the structure version

The [structure version](docs/reference/repo-structure.md#structure-version) goes up when an existing repository has
to change to follow the structure. This repository and kubectl-gs have to agree on it, and nothing checks that they
do. When you bump it:

1. Record what changed in the [CHANGELOG](CHANGELOG.md).
1. Bump `StructureVersion` in
   [kubectl-gs](https://github.com/giantswarm/kubectl-gs/blob/main/internal/gitops/metadata/types.go) to match.
1. Add the migration from the previous version to the
   [kubectl-gs migration registry](https://github.com/giantswarm/kubectl-gs/blob/main/internal/gitops/migration/registry.go),
   so `kubectl gs gitops upgrade` can bring existing repositories along. A kubectl-gs test fails when a version has
   no migration.

Note that migrations only change the layers that `kubectl gs gitops` records. If a structure change also needs files
outside every layer, such as the ones `gitops init` creates at the repository root, or moves a layer to a new path,
extend `kubectl gs gitops upgrade` first.
