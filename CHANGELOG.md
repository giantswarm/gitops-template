# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Semantic YAML diff PR comments via the new `yaml-diff` workflow (calls `giantswarm/github-workflows/.github/workflows/yaml-diff.yaml`). Key reordering without value changes no longer shows up as noise in PR reviews. Alphabetical key-ordering enforcement in `.yamllint` is unchanged in this release; it will be dropped in a follow-up once the bot has run on real PRs. See [giantswarm/roadmap#4121](https://github.com/giantswarm/roadmap/issues/4121).

### Changed

- Bump `dyff_ver` from `1.5.4` to `1.7.1` in the existing rendered-manifest diff job (`validate.yaml`), to standardize on the version used by the new `yaml-diff` workflow.
- migrated `.spec.config` to `.spec.extraConfigs`
- Templates: Rename `nginx-ingress-controller` to `ingress-nginx`. ([#85](https://github.com/giantswarm/gitops-template/pull/85))

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
