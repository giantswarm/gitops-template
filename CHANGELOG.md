# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

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
- Corrects an earlier entry in this section: the `simple-db-app` `ImageRepository`
  was repointed at `gsoci.azurecr.io/charts/giantswarm/simple-db-app`, but that
  repository does not exist -- the chart was never published to `gsoci` and
  `simple-db-app` is not in the `giantswarm` catalog. The example is removed
  instead, see the Removed section below. See
  [giantswarm/giantswarm#35783](https://github.com/giantswarm/giantswarm/issues/35783).
- Example app versions now match what the `giantswarm` catalog actually serves:
  `hello-world` `0.2.0` -> `3.2.2`, `ingress-nginx` `3.0.0` -> `4.3.5`,
  `cert-manager-app` `2.12.0` -> `4.1.1`, `flux-app` `0.11.0` -> `1.9.1`.
  The `hello-world` `App` CRs also referenced a non-existent catalog entry
  `hello-world-app`; the entry is called `hello-world`.
- Example `hello-world` and `ingress-nginx` values now use the keys their charts
  actually accept. The previous `admin_login` / `db_config` / `thread_pool_size`
  values were invented for the removed `simple-db` demo, and `ingress-nginx`
  moved `configmap:` under `controller.config:`.
- `ImagePolicy` semver ranges follow the new major: `>=3.0.0-0` for the `-dev`
  stage (the `-0` is required, or the range excludes every pre-release tag) and
  `>=3.0.0 <4.0.0` for staging.
- The `$imagepolicy` setter marker on the automatic-updates example named
  namespace `default`, but the `ImagePolicy` it refers to lives in
  `org-${organization}`.

### Removed

- The `simple-db-app` demo app (`bases/apps/simple-db`, its `App`,
  `ImageRepository` and `ImagePolicy` entries in the environment stages, its
  app-set config and its `tests/ats` assertions). The source repository is gone
  and the chart is published nowhere, so there is no version of it that works.
  The `hello-web-app` app set now bundles `hello-world` alone. Closes
  [#131](https://github.com/giantswarm/gitops-template/issues/131).
- Dropped the alphabetical `key-ordering` rule from `.yamllint`. It only
  existed to keep PR diffs readable; the `yaml-diff` bot now provides clean
  semantic diffs (ignoring key reordering), so the restriction is no longer
  needed. Closes
  [giantswarm/roadmap#4121](https://github.com/giantswarm/roadmap/issues/4121).

### Fixed

- `tests/ats`: pin every CAPI provider to an explicit release URL, via a
  generated `clusterctl` config. The suite has failed as "Cannot bootstrap CAPI"
  on every run since 2026-08-19.

  The stock provider URLs end in `/releases/latest/`, and `clusterctl` reads the
  version straight out of that path when it builds its repository client, before
  it considers what `--core`/`--infrastructure` asked for. Resolving "latest"
  means reading the newest `cluster-api` release's `metadata.yaml`, finding the
  release series that serves the `v1beta1` contract `clusterctl` v1.2.0 speaks
  (1.10), then searching for a 1.10.x tag -- a search that only covers the 30
  newest releases, because `clusterctl` requests the release list with no paging
  options. `cluster-api` published its 30th release since v1.10.10 on
  2026-08-11, so 1.10.x dropped out of that window and the lookup has returned
  nothing since, surfaced as the misleading "failed to find releases tagged with
  a valid semantic version number".

  The pins cover the providers `clusterctl init` installs implicitly too -- the
  core provider and the kubeadm bootstrap/control-plane pair -- since those
  carried the `latest` URLs. The core provider is pinned to `v1.10.10`, the
  newest release of the series the resolution was selecting until it broke, so
  the suite keeps testing against the CAPI version it already was. Going past
  the `v1beta1` contract needs a newer `clusterctl` than the `1.2.0` the
  workflow installs, plus newer infrastructure providers.

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
