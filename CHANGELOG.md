# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- The repository structure is now versioned. The layout described in
  `docs/repo_structure.md` is **structure version 1**, and a new
  [Structure Version](docs/repo_structure.md#structure-version) section
  defines what does and does not warrant a bump. `kubectl gs gitops` records
  the version in a `.gitops-metadata.yaml` file at the root of the
  repositories it generates, and `kubectl gs gitops check` reports the parts
  of a repository that were generated with an older one.
  Bumping the version here requires bumping `StructureVersion` in
  `kubectl-gs` to match; the two are kept in lockstep by hand.
  See [giantswarm/giantswarm#23540](https://github.com/giantswarm/giantswarm/issues/23540).
- Semantic YAML diff PR comments via the new `yaml-diff` workflow
  (calls `giantswarm/github-workflows/.github/workflows/yaml-diff.yaml`).
  Key reordering without value changes no longer shows up as noise in PR
  reviews. Alphabetical key-ordering enforcement in `.yamllint` is
  unchanged in this release; it will be dropped in a follow-up once the
  bot has run on real PRs.
  See [giantswarm/roadmap#4121](https://github.com/giantswarm/roadmap/issues/4121).

### Changed

- CI: replaced the hand-maintained `validate.yaml` and `basic.yml` with a thin
  caller to the new reusable
  `giantswarm/github-workflows/.github/workflows/gitops-validate.yaml`. Behaviour
  is unchanged (pre-commit, `./tools/test-all-ff validate`, rendered-manifest diff,
  and the `tests/ats` kind e2e); the GitHub Actions pins are now maintained
  centrally and on current releases, clearing the Node 20 / `set-output`
  deprecation warnings.
- Bump `dyff_ver` from `1.5.4` to `1.7.1` in the existing rendered-manifest
  diff job (`validate.yaml`), to standardize on the version used by the new
  `yaml-diff` workflow.
- migrated `.spec.config` to `.spec.extraConfigs`
- Templates: Rename `nginx-ingress-controller` to `ingress-nginx`. ([#85](https://github.com/giantswarm/gitops-template/pull/85))
- Example `simple-db-app` `ImageRepository` now points at the current registry
  `gsoci.azurecr.io/charts/giantswarm/simple-db-app` instead of the
  decommissioned `giantswarmpublic.azurecr.io/giantswarm-catalog/simple-db-app`
  (bases, `add_wc_environments.md` docs, and `tests/ats` fixtures), matching the
  sibling `hello-world` example. See
  [giantswarm/giantswarm#35783](https://github.com/giantswarm/giantswarm/issues/35783).

### Removed

- Dropped the alphabetical `key-ordering` rule from `.yamllint`. It only
  existed to keep PR diffs readable; the `yaml-diff` bot now provides clean
  semantic diffs (ignoring key reordering), so the restriction is no longer
  needed. Closes
  [giantswarm/roadmap#4121](https://github.com/giantswarm/roadmap/issues/4121).

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
