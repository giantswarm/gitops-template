# Contributing

Thanks for working on the template itself. A change here is a change to what every customer copies, so it comes with
its documentation and its tests, and every example has to get `Ready` in CI.

- Run [pre-commit](docs/how-to/check-changes.md#run-pre-commit) and
  [`tools/test-all-ff validate`](docs/how-to/check-changes.md#validate-with-test-all-ff) before you push.
- A new example directory needs a `README.md` that says what it shows and what to change when you copy it;
  `tools/check-directory-readmes` fails without one, see [tools](tools/README.md).
- A new cluster or app in the examples needs what the kind test checks it with, see
  [What the kind test does](docs/tutorials/advanced/testing.md#what-the-kind-test-does) and
  [CI checks](docs/reference/ci-checks.md).
- A change to documented behaviour updates the documentation in the same pull request.

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
