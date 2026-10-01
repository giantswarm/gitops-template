# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- `renovate.json5` extending the shared
  [giantswarm/renovate-presets](https://github.com/giantswarm/renovate-presets)
  default, so dependency updates are managed here the same way as in every other
  Giant Swarm repository. The opt-in `pre-commit` manager is enabled on top: the
  hooks in `.pre-commit-config.yaml` are the only dependencies here that have
  actually gone stale. Closes
  [giantswarm/roadmap#3943](https://github.com/giantswarm/roadmap/issues/3943).
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

- Every workload app in the template is now a Flux `HelmRelease` paired with an
  `OCIRepository`, replacing the 20 App CRs that used to render from `bases/` and
  `management-clusters/`. The App Platform `catalog` + `name` + `version` triple
  becomes an `OCIRepository` pointing straight at
  `oci://gsoci.azurecr.io/charts/giantswarm/<chart>` with the version as
  `spec.ref.tag`, and the App CR's `config`/`extraConfigs`/`userConfig` become
  `spec.valuesFrom` entries on the `HelmRelease`. Where an App CR had
  `kubeConfig.inCluster: false`, the `HelmRelease` names the workload cluster's
  `<cluster>-kubeconfig` secret explicitly. First step of
  [giantswarm/roadmap#4380](https://github.com/giantswarm/roadmap/issues/4380).
  Notable consequences:
  - Kustomize patches that pinned a version through `/spec/version` on an `App`
    now target `/spec/ref/tag` on the `OCIRepository`. This includes the
    `$imagepolicy` setter markers used by the automatic-updates example, so image
    automation keeps working against the chart tag.
  - `spec.valuesFrom` is a list and `kustomize` has no merge strategy for
    `HelmRelease`, so a strategic-merge patch replaces it rather than appending.
    The app-set and app-template overlays therefore restate the entry they
    inherit alongside the one they add.
  - App CRs could reference a ConfigMap or Secret in another namespace;
    `spec.valuesFrom` cannot. Two example references that pointed at namespaces
    with nothing in them (`org-multi-project`, `hello-world-app`) now resolve
    against the namespace the `HelmRelease` lives in, which is where the
    ConfigMaps were generated all along.
  - The cluster App CRs (`cluster-aws`, from `bases/clusters/capa/template`) are
    deliberately **not** converted here and still use App Platform.
- CI: the kind-based e2e suite waits for every `HelmRelease` to go ready, and
  none of the ones in this template can -- they all target a workload cluster
  that does not exist in the test environment. They are listed in the
  `gitops_ignored_objects` input in `.github/workflows/validate.yaml`, next to
  the Kustomization that was already ignored for the same reason. Their rendered
  manifests are still asserted through `tests/ats/assertions`.
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

- The `giantswarm-catalog-oci` `Catalog` CRs under the two out-of-band workload
  clusters' `mapi/automatic-updates/`. They existed only so the automatic-updates
  App CR had a catalog to resolve its chart from; an `OCIRepository` addresses the
  registry directly, so nothing referenced them any more.
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
