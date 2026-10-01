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

- Envoy Gateway replaces ingress-nginx as the example edge. The new
  `bases/apps/envoy-gateway` App Template installs `gateway-api-crds`,
  `envoy-gateway` and `gateway-api-config` into the workload cluster as three
  chained `HelmRelease`s, each with its chart from an `OCIRepository`. It is the
  first HelmRelease-based App Template here. The resources follow the shape
  [giantswarm/appcr-to-helmrelease-converter](https://github.com/giantswarm/appcr-to-helmrelease-converter)
  emits for a migrated App CR, so converted and new apps look alike:
  - the chart version pinned in `spec.ref.tag`, with a `repo:` comment Renovate
    uses to propose upgrades; `renovate.json5` gains the regex manager for it, as
    the preset's `repo:` patterns don't cover `tag:`
  - values layered through `valuesFrom`, in this order: the cluster values
    ConfigMap, the template defaults, then optional `-template-values` (cluster
    template), `-user-values` (ConfigMap) and `-user-secrets` (SOPS-encrypted
    Secret)
  - 10 install and upgrade retries, rollback on a failed upgrade, 10m timeout
  - `giantswarm.io/cluster` labels

  `hello-world` is now exposed through an `HTTPRoute` on the `giantswarm-default`
  Gateway as `hello.<cluster base domain>`, instead of an Ingress. The
  `hello_app_cluster` template adds the `hello` subdomain to the Gateway's DNS
  record and certificate. The hello-world App CRs now carry the
  `giantswarm.io/cluster` label. App Platform needs it to add the cluster values
  that the hostname is built from. The kind test now checks that
  OCIRepositories are ready. It skips HelmReleases that deploy to a workload
  cluster, since the test has none. Part of
  [giantswarm/roadmap#4380](https://github.com/giantswarm/roadmap/issues/4380).

  **Prerequisites on the workload cluster:** the Giant Swarm default apps
  (cert-manager, external-dns, Kyverno, Cilium, the monitoring CRDs), plus:
  - Gateway API support enabled in cert-manager
  - on AWS, aws-load-balancer-controller

  **Migrating a fork:**
  - The per-cluster Kustomizations use `prune: false`, so the existing
    ingress-nginx App CRs stay after the update. Delete them by hand once traffic
    runs through the Gateway.
  - Remove any `gateway-api-bundle` app installed on the cluster first. It
    installs the same charts under other release names.
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
- The `WC_NAME` example labelled its `App` CRs `giantswarm.io/cluster: WC_NAME`
  instead of the cluster name. App Platform uses this label to find the
  cluster's `<cluster>-cluster-values` ConfigMap and `<cluster>-kubeconfig`
  Secret, and app-operator uses it to select the `App`, so the literal
  placeholder broke both. The label is now `${cluster_name}`, substituted by the
  Flux `Kustomization`. The same label on the `hello-world-automatic-updates`
  `App` in the two out-of-band examples used `${workload_cluster_name}`, which
  no `Kustomization` substitutes, so it rendered empty; it is now
  `${cluster_name}` too. The other `App`s in the out-of-band examples had no
  `giantswarm.io/cluster` label at all; their `apps` and `hello-web-app-1`
  kustomizations now add it. `tests/ats` asserts the label and the
  `hello-web-app-1` `userConfig` namespace for both out-of-band clusters.
- The `hello-web-app-1` app set in the two out-of-band examples pointed the
  `App`'s `userConfig` at a ConfigMap in namespace `hello-world-app`, but the
  ConfigMap is generated in `org-${organization}`. It now points there.

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
