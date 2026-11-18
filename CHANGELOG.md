# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Every ConfigMap and Secret that a `HelmRelease` lists in `valuesFrom` carries the
  `reconcile.fluxcd.io/watch: Enabled` label, the generated ones included, so helm-controller applies a change to the
  values as soon as it's made instead of at the `HelmRelease`'s next `interval`. The guides' examples carry it too.
  `tools/validate-helm-values` fails for such an object without the label, and the kind test checks that a change to
  a values ConfigMap is reconciled within 90 seconds. ([#251](https://github.com/giantswarm/gitops-template/issues/251))
- The kind test checks the node pools of every workload cluster. It merges the values of each cluster's
  `HelmRelease` as Flux applied it, `valuesFrom` and `spec.values`, the way helm-controller does, and compares the
  node pools with `EXPECTED_NODE_POOLS` in `tests/ats/node_pools.py`: the production clusters get the stage's
  `nodepool0` and their region's extra pool, dev and staging have no pools of their own and get the chart's defaults,
  and the `WC_NAME` and out-of-band clusters get `workers`. ([#206](https://github.com/giantswarm/gitops-template/issues/206))
- The kind test reconciles the `-direct` out-of-band example, which CI ignored because it targets a workload
  cluster. `tests/ats` creates a vCluster in the kind cluster as that workload cluster and puts its kubeconfig in the
  `out-of-band-no-flux-kubeconfig` Secret the `Kustomization` reads. The `Kustomization` has to get ready, and
  the files in `tests/ats/assertions/exists-in-workload-cluster` are checked against the vCluster.
  The vCluster chart (0.37.6) and its Kubernetes image (v1.36.6) are pinned in `tests/ats/conftest.py`.
  `gitops_ignored_objects` in `validate.yaml` is empty now. ([#224](https://github.com/giantswarm/gitops-template/issues/224))
- A CAPA cluster base in `bases/clusters/capa/release` for the `release-aws` chart, and an example workload
  cluster that uses it. The base is an overlay of `bases/clusters/capa/template`. The App's version is the
  Giant Swarm release, taken from the `release` variable, so the release lives in git. Use it for releases that
  have a `release-aws` chart, which is every release from v34.0.0 on. `bases/clusters/capa/template` stays the
  base for older releases and for Release CRs created by hand.
- `renovate.json5` extending the shared
  [giantswarm/renovate-presets](https://github.com/giantswarm/renovate-presets)
  default, so dependency updates are managed here the same way as in every other
  Giant Swarm repository. The opt-in `pre-commit` manager is enabled on top: the
  hooks in `.pre-commit-config.yaml` are the only dependencies here that have
  actually gone stale. Closes
  [giantswarm/roadmap#3943](https://github.com/giantswarm/roadmap/issues/3943).
- The repository structure is now versioned. The layout described in
  `docs/reference/repo-structure.md` is **structure version 1**, and a new
  [Structure Version](docs/reference/repo-structure.md#structure-version) section
  defines what does and does not warrant a bump. `kubectl gs gitops` records
  the version in a `.gitops-metadata.yaml` file at the root of the
  repositories it generates, and `kubectl gs gitops check` reports the parts
  of a repository that were generated with an older one.
  Bumping the version here requires bumping `StructureVersion` in
  `kubectl-gs` to match; the two are kept in lockstep by hand.
  See [giantswarm/giantswarm#23540](https://github.com/giantswarm/giantswarm/issues/23540).
- The [Structure Version](docs/reference/repo-structure.md#structure-version) section
  now covers `kubectl gs gitops upgrade`, which brings a repository generated
  with an older structure version up to date, and requires every version bump
  to ship with a migration in `kubectl-gs`.
- Semantic YAML diff PR comments via the new `yaml-diff` workflow
  (calls `giantswarm/github-workflows/.github/workflows/yaml-diff.yaml`).
  Key reordering without value changes no longer shows up as noise in PR
  reviews. Alphabetical key-ordering enforcement in `.yamllint` is
  unchanged in this release; it will be dropped in a follow-up once the
  bot has run on real PRs.
  See [giantswarm/roadmap#4121](https://github.com/giantswarm/roadmap/issues/4121).
- `tests/ats` asserts the ConfigMaps, `HelmRelease`s and `OCIRepository`s of the `hello-app-prod-usw` example
  cluster, which only had its `Kustomization` checked. Its region values are asserted as they are today, including
  the bugs [#204](https://github.com/giantswarm/gitops-template/issues/204) and
  [#206](https://github.com/giantswarm/gitops-template/issues/206) will fix, as for `hello-app-prod-euc`.
  The assertions now also check the order of `valuesFrom`, which decides how Helm merges values; other lists are
  still compared without order. ([#223](https://github.com/giantswarm/gitops-template/issues/223))

- `tools/validate-helm-values`, which renders the chart of every Flux
  `HelmRelease` with the values it gets from `valuesFrom` and `spec.values`,
  and fails when Helm rejects them. A misspelled key such as `instanceTyp` now
  fails the `validate` job instead of the reconciliation. `test-all-ff
  validate` runs it for every `Kustomization`. Values that only exist at
  runtime, like the `<cluster>-cluster-values` ConfigMap, come from stubs in
  `tools/values-stubs`. `tools/validate-helm-values.ignore` lists four example
  clusters whose names are longer than the 20 characters `release-aws` allows.
  Closes [#220](https://github.com/giantswarm/gitops-template/issues/220).

### Changed

- A cluster's secondary apps install once the cluster is ready. The `WC_NAME` and out-of-band example clusters each
  have two `Kustomization`s. The cluster's, in the existing file, applies `mapi/cluster`: the cluster and its base
  apps, which now live in `mapi/cluster/apps`, such as the Gateway API stack of the out-of-band clusters. Its health
  check waits until Cluster API reports the `Cluster` `Available`, with a `timeout` of 30 minutes. While the cluster
  isn't `Available`, each reconciliation of that `Kustomization` waits for up to those 30 minutes, so a fix pushed to
  the cluster's files is only applied once the wait runs out, and the apps `Kustomization` reports
  `DependencyNotReady` all the while. The new apps
  `Kustomization`, `WC_NAME-apps.yaml` and `*_OUT_OF_BAND_*-apps.yaml`, applies the rest of `mapi`, the secondary apps
  and App Sets that the new `mapi/kustomization.yaml` lists, and depends on the cluster's. `mapi/app_sets` has a
  `kustomization.yaml` that lists the cluster's App Sets. The `HELLO_APP_*` clusters have no apps and keep a single
  `Kustomization`. The kind test creates stand-in `Cluster`s and checks that the base apps don't wait for them and
  the secondary apps do; `test_prune` deletes both of the cluster's `Kustomization`s. A new `pre-commit` hook,
  `tools/check-kustomization-paths`, checks that every Flux `Kustomization`'s path exists and builds.
  `kubectl gs gitops add workload-cluster` still writes a single `Kustomization`.
  ([#210](https://github.com/giantswarm/gitops-template/issues/210))
  To split a running cluster's `Kustomization`:
  1. Move the base apps into `mapi/cluster/apps` and list them in `mapi/cluster/kustomization.yaml`. If the cluster
     has App Sets, add `mapi/app_sets/kustomization.yaml` listing each App Set's directory: Flux generated that list
     until now, and without it `mapi/app_sets` doesn't build. Add `mapi/kustomization.yaml`, listing `cluster/`,
     `apps/` and, if the cluster has App Sets, `app_sets/` for now. Anything else under `mapi/` that
     `mapi/kustomization.yaml` doesn't list stops being applied, and Flux deletes it: list it, or move it into one of
     those directories first.
  1. Add the apps `Kustomization`, with the cluster's in `dependsOn`, the same `postBuild` substitutions and SOPS
     `decryption` as the cluster's, and list it in `workload-clusters/kustomization.yaml`.
  1. In Git, add the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation to every object that changes owner in the
     next step, so neither `Kustomization` deletes it while the other takes it over: every object in `mapi/apps`,
     `mapi/app_sets` and `mapi/cluster`, including the `OCIRepository`s, ConfigMaps and Secrets, not only the
     `HelmRelease`s.
  1. Then, in one commit, narrow the cluster `Kustomization`'s `path` to `mapi/cluster`, add its health check and
     `timeout`, and remove `cluster/` from `mapi/kustomization.yaml`.
  1. Remove the annotation in Git from each of those objects again once it's in the inventory of its new `Kustomization`
     (`kubectl get kustomization NAME -n default -o yaml`, `status.inventory`). Keep it on the objects that carry it
     anyway, such as the cluster's `HelmRelease`.
- The `hello-world` base in `bases/apps/hello-world` and the `cert-manager` app of the `WC_NAME` example
  install into their own namespace in the workload cluster, `hello-world` and `cert-manager`, with Helm storage in
  the same namespace. They used `org-${organization}`, which created an organisation namespace in the workload
  cluster. The `HelmRelease`s stay in the organisation namespace on the management cluster. The `cert-manager` app no
  longer installs the cert-manager CRDs (`cert-manager.crds.enabled: false`): the Giant Swarm release installs them.
  ([#207](https://github.com/giantswarm/gitops-template/issues/207))
  If you upgrade a cluster that runs one of these apps:
  - Flux uninstalls a release whose target or storage namespace changes and installs it again in the new namespace,
    in separate reconciliations. Until the new install is ready, the app isn't running: `hello-world` has no Service
    or `HTTPRoute`. cert-manager has no controller, and its webhook configurations are deleted with the release, so
    the API server stores changes to `Certificate`s without validating or defaulting them, and nothing acts on them
    until the reinstall. An invalid spec is stored and fails later.
  - The cert-manager CRDs, and with them the `Certificate`s and `ClusterIssuer`s, survive the uninstall only because
    `cert-manager-app` keeps its CRDs by default (`cert-manager.crds.keep: true`). With `keep` off, or for a chart
    whose CRDs don't have the `helm.sh/resource-policy: keep` annotation, the uninstall deletes the CRDs and every
    resource of those kinds.
  - cert-manager reads the Secrets of `ClusterIssuer`s from its own namespace (`--cluster-resource-namespace`). Before
    you upgrade, copy the ACME account key, and any CA key pairs or credentials you created yourself, from
    `org-<organisation>` to `cert-manager` in the workload cluster. Otherwise the `ClusterIssuer`s aren't ready and
    renewals fail, and a missing ACME account key registers a new account.
  - The `org-<organisation>` namespace in the workload cluster isn't part of the release, so nothing deletes it.
    Delete it once it holds nothing you need.
- Every Flux `Kustomization` has `prune: true`, so deleting a file from Git deletes what it created, such as an app.
  The objects whose deletion would delete a cluster, the cluster `HelmRelease` in
  `bases/clusters/capa/template` and the `Organization`, and the SOPS key `Secret`s Flux decrypts with, have the
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, so Flux keeps them, and the
  `giantswarm.io/prevent-deletion: "true"` label, so the `kyverno-policies-ux` policies refuse to delete them, whoever
  asks, until the label is removed. `docs/how-it-works.md` explains what is deleted and what is kept, and the guides
  use `prune: true`, add the annotation and the label where `kubectl gs` doesn't yet, and delete a cluster by removing
  the label from its `HelmRelease` and deleting it by hand. The kind test checks both. ([#208](https://github.com/giantswarm/gitops-template/issues/208))
- Each example workload cluster with encrypted files has its own SOPS key and its own `.sops.yaml` rule for its
  `mapi/` directory, as `kubectl gs gitops add encryption --workload-cluster <WC> --target mapi/` creates, instead of
  one rule for every workload cluster. The examples reuse the existing demo keys rather than the tool's per-cluster
  names: `WC_NAME_OUT_OF_BAND_FLUX_APP` keeps the `WC_NAME` key, and `WC_NAME_OUT_OF_BAND_NO_FLUX_APP` uses the
  `FROM_TEMPLATE_WC_NAME` key, which nothing used before. Its `secret.enc.yaml` is encrypted with that key, with the
  same values, and its `Kustomization` decrypts with `sops-gpg-from-template-wc-name`. `WC_NAME` and the
  `HELLO_APP_*` clusters have no rule now: encrypting a file for one of them fails with "no matching creation rules
  found" until you add its key and rule as the
  [WC structure guide](docs/add_wc_structure.md#create-flux-gpg-regular-key-pair-optional-step) describes. The
  [add an App](docs/guides/add-app.md) and [automatic updates](docs/guides/automatic-updates.md) guides point there.
  ([#212](https://github.com/giantswarm/gitops-template/issues/212))
- `tools/fake-flux` runs `flux build` with `--strict-substitute`, so `tools/test-all-ff validate` fails when a
  `Kustomization`'s manifests use a variable that its `spec.postBuild.substitute` doesn't set. Flux replaces such a
  variable with an empty string: a cluster without `release` gets an `OCIRepository` with no tag, which Flux resolves
  to the chart's `latest` tag. `test-all-ff validate` checks this with the fixture in
  `tools/testdata/unset-variable`, which discovery leaves out. A `Kustomization` that doesn't build no longer stops
  `test-all-ff validate`: it is reported, and the others are still checked. [How it
  works](docs/how-it-works.md#bases-and-variables) lists the variables the bases use.
  ([#250](https://github.com/giantswarm/gitops-template/issues/250))
- The example `kustomization.yaml` files, and the one in [Add Workload Cluster instance](docs/add_wc_instance.md),
  set their labels with `labels` instead of `commonLabels`, which kustomize v5 deprecates. None of the objects they
  build has a selector or a pod template, so the rendered manifests are unchanged. `kubectl gs gitops add
  workload-cluster` still writes `commonLabels`; the guide says how to move them to `labels`.
  ([#213](https://github.com/giantswarm/gitops-template/issues/213))
- Renovate updates the versions CI pins in plain variables: the shared workflow's version inputs in
  `.github/workflows/validate.yaml` (Python, kubeconform, kind, flux-app, apptestctl), `KUBERNETES_VERSION` and
  `FLUX_VERSION` in `tools/test-all-ff`, and `CAPI_VERSION` and `VCLUSTER_CHART_VERSION` in `tests/ats/conftest.py`.
  Each has a `# renovate:` comment naming its datasource, read by a regex manager in `renovate.json5`.
  ([#228](https://github.com/giantswarm/gitops-template/issues/228))
- The docs state that their `kubectl gs` commands need kubectl-gs 6.0.0 or newer. A table in
  [Appendices](docs/appendices.md#kubectl-gs-version) lists the version that added each command and flag the docs
  use, and the guides link to it. ([#236](https://github.com/giantswarm/gitops-template/issues/236))
- Renovate updates the chart tags pinned in `OCIRepository` `spec.ref.tag` (hello-world, envoy-gateway,
  gateway-api-config, gateway-api-crds, cert-manager-app, flux-app) and the Giant Swarm release. The flux manager now
  reads every YAML file, not only `gotk-components.yaml`. It doesn't see tags set by kustomize patches or postBuild
  variables, so those have a `# renovate:` comment: the release (the `release-aws` chart's tag) where the `release`
  variable is set in the `WC_NAME*.yaml` Kustomizations and where each stage patches it in, and hello-world where the
  `hello-web-app` app set and the prod stage patch it. The test assertions repeat these versions, and Renovate updates
  them in the same PR as the files they check. Prod's own pins, hello-world and the release in
  `bases/environments/stages/prod` and in the `hello-app-prod-*` clusters' assertions, get a separate PR on a
  `renovate/prod-*` branch that isn't automerged: merge it after staging has run the new version. For hello-world, the
  other PR changes what the out-of-band clusters render (dev and staging follow a semver range instead), and prod's
  patch overrides the app set's. For the release, it changes what the `WC_NAME*` clusters, dev and staging render.
  Prod renders the new version only once its own PR is merged. The prod split gates only hello-world and the Giant
  Swarm release: the charts prod takes from the bases unpatched (envoy-gateway, gateway-api-config,
  gateway-api-crds) follow the bases in a single PR, and outside prod's own PR, patch updates of charts automerge.
  Giant Swarm release updates never automerge, in any PR, because they roll the cluster's nodes. The release's TODO
  comment no longer names the version, which Renovate would leave behind.
  ([#226](https://github.com/giantswarm/gitops-template/issues/226))
- Four example clusters have shorter names, because `release-aws` rejects a cluster name longer than 20 characters:
  `hello-app-prod-us-west` is `hello-app-prod-usw`, `hello-app-prod-eu-central` is `hello-app-prod-euc`,
  `mapi-out-of-band-no-flux` is `out-of-band-no-flux` and `mapi-out-of-band-flux-app` is `out-of-band-flux-app`.
  `tools/validate-helm-values.ignore`, which listed them as known failures, is gone, so CI checks their values,
  including the region, like those of every other cluster. The getting-started guides state the limit.
  ([#274](https://github.com/giantswarm/gitops-template/issues/274))
- CI: the kind test installs only the Cluster API v1.14.4 core CRDs, the CAPI version of the management clusters,
  instead of Cluster API, CAPA and CAPZ with their controllers. Nothing in the template or the tests used them, and
  this repository doesn't test cluster creation. `validate.yaml` no longer sets `clusterctl_ver`.
  See [Configuring extra validation](docs/guides/ci-validation.md#cluster-api).
  ([#289](https://github.com/giantswarm/gitops-template/issues/289))
- CI: the kind test runs on Kubernetes v1.36, the minor version of the management clusters, instead of v1.23 from
  2022. `validate.yaml` sets kind v0.32.0 (`kindest/node:v1.36.1`), clusterctl v1.14.4, flux-app 1.12.2 and
  apptestctl 0.27.0. `tests/ats` installs Cluster API v1.14.4, CAPA v2.11.1 and CAPZ v1.27.0, the upstream releases
  the management clusters run, instead of v1.10.10, v1.2.0 and v1.0.1. pytest prints the test cluster's Kubernetes
  version in its header. ([#279](https://github.com/giantswarm/gitops-template/issues/279))
- CI: `validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call `giantswarm/github-workflows` at a commit
  SHA with a `# main` comment instead of at `@main`, so a change upstream no longer changes this repository's CI
  without a commit here. Renovate moves the SHA to the head of `main` and automerges it. See
  [Configuring extra validation](docs/guides/ci-validation.md).
  ([#227](https://github.com/giantswarm/gitops-template/issues/227))
- **Breaking:** the template uses the file and resource names `kubectl gs gitops` 6.0.4 generates, so
  `kubectl gs gitops check --adopt` records every example app and `kubectl gs gitops add automatic-update` works on
  them. Forks keep working as they are; to move one, follow
  [Move a fork to the kubectl-gs file and resource names](docs/guides/kubectl-gs-names.md).
  - Apps keep their `HelmRelease` in `helm-release.yaml` and their `OCIRepository` in `oci-repository.yaml`, instead
    of `helmrelease.yaml` and `ocirepository.yaml`. The envoy-gateway App Template has a directory per chart instead
    of `helmreleases.yaml` and `ocirepositories.yaml`, so every file holds one resource.
    ([#197](https://github.com/giantswarm/gitops-template/issues/197))
  - A workload cluster's values are in `cluster_userconfig.yaml` and `patch_cluster_userconfig.yaml`, and the
    ConfigMap is `${cluster_name}-cluster-userconfig`, instead of `cluster_user_config.yaml`, `patch_user_config.yaml`
    and `${cluster_name}-user-config`. ([#198](https://github.com/giantswarm/gitops-template/issues/198))
  - The workload cluster Flux `Kustomization`s are named `MC_NAME-clusters-WC_NAME`, for example
    `mc-name-clusters-capi-wc-name` instead of `clusters-capi-wc-name`. The CI validation ignores the out-of-band
    `Kustomization` by its new name through the `gitops_ignored_objects` input.
    ([#199](https://github.com/giantswarm/gitops-template/issues/199))
  - `bases/clusters/capa/template` has the files `kubectl gs gitops add base --provider capa` writes: one
    `cluster.yaml` with the `OCIRepository` and the `HelmRelease`, with the CLI's field values, and a
    `cluster_config.yaml` with the CLI's defaults. It keeps `global.metadata.description` and leaves out the empty
    `nodepool0` node pool, see its readme. ([#200](https://github.com/giantswarm/gitops-template/issues/200))
- **Breaking:** every cluster sets its region. Without `global.providerSpecific.region`, `release-aws` takes the
  region of the management cluster's nodes, so a cluster would be created where its management cluster runs.
  - A region in `bases/environments/regions` is now a kustomize Component that creates `${cluster_name}-region-config`
    with the region and appends it to the cluster's `valuesFrom`. `us_west` uses `us-west-2` and its zones instead of
    `eu-west-1a` ([#204](https://github.com/giantswarm/gitops-template/issues/204)), and each region sets
    `global.providerSpecific.region` ([#205](https://github.com/giantswarm/gitops-template/issues/205)). The dev,
    staging, `WC_NAME` and out-of-band example clusters use `eu_central`.
  - A region's extra node pool, `large` in the region's zones, is a second `node_pool` component that only the prod
    clusters add, next to the stage's `nodepool0`. The regions no longer have a placeholder security group, and the
    `WC_NAME` and out-of-band examples name their pool `workers` instead of `xxxxx`.
  - The `hello_app_cluster` template no longer appends the cluster's own values itself: a cluster lists its region,
    then the template's `userconfig` component, under `components:`, so its own values come last. No cluster inserts
    a ConfigMap at a fixed `valuesFrom` position any more.
  - The `release-aws` stub of `tools/validate-helm-values` no longer sets a region, so a cluster without one fails
    with the chart's "Unable to default the region". This doesn't cover the clusters listed in
    `validate-helm-values.ignore` until [#274](https://github.com/giantswarm/gitops-template/issues/274) removes that
    file. `tools/test-all-ff validate` checks this with `tools/testdata/release-aws-without-region.yaml`. The getting
    started guides and the cluster in `docs/how-it-works.md` add a region too.

  **Migrating a fork:**
  - In each cluster's `mapi/cluster/kustomization.yaml`, move the region from `resources:` to `components:`, and add a
    region to every cluster that has none.
  - Drop any patch that inserts the region's ConfigMap at `/spec/valuesFrom/1`.
  - A cluster made from the `hello_app_cluster` template lists, under `components:`, its region, then its region's
    `node_pool` if it wants the extra pool, and last `bases/cluster_templates/hello_app_cluster/userconfig`. Without
    the `userconfig` component the cluster loses its own values and those of its stage, and CI doesn't catch it.
- The repository structure is version 2. Clusters and apps are deployed with Flux `HelmRelease`s, and nothing in the
  repository deploys or patches an App CR. `bases/clusters/capa/template`, the App CR base for the `cluster-aws` chart,
  is gone, so releases before v34.0.0 and Release CRs created by hand are no longer supported.
  `bases/clusters/capa/release` takes its place as `bases/clusters/capa/template`, the path
  `kubectl gs gitops add base` generates. The `WC_NAME` and out-of-band example clusters are built on it and set the
  `release` variable. `WC_NAME_RELEASE` is removed, because `WC_NAME` is now the same cluster. kubectl-gs 6.0.0
  generates this structure, and `kubectl gs gitops upgrade` moves a fork from version 1 once its App CRs are gone.
- `bases/clusters/capa/release` deploys the `release-aws` chart as a Flux `OCIRepository` and `HelmRelease` instead of
  an App CR, like `kubectl gs template cluster` does since kubectl-gs 5.13.0. The release is the `OCIRepository` tag. A
  cluster adds its own values with a ConfigMap and a patch that appends it to the `HelmRelease`'s `valuesFrom`, the same
  layout `kubectl gs gitops add workload-cluster` generates since giantswarm/kubectl-gs#2274. Stages set the release on
  the `OCIRepository`, and every cluster adds its region. Clusters created from the old release base are App CRs, and
  moving them needs a hand-over that doesn't reinstall them. See
  [giantswarm/roadmap#4380](https://github.com/giantswarm/roadmap/issues/4380).
- The `hello_app_cluster` cluster template and its dev, staging and prod stages build on
  `bases/clusters/capa/release`. Each stage sets the release as the cluster App's version, `36.2.0` in the
  examples, and no longer sets `global.release.version` in its values. The dev and staging stages have no
  values file left. `docs/add_wc_instance.md` and `docs/guides/environments.md` only describe the release base.
- Envoy Gateway replaces ingress-nginx as the example edge. The new
  `bases/apps/envoy-gateway` App Template installs `gateway-api-crds`,
  `envoy-gateway` and `gateway-api-config` into the workload cluster as three
  chained `HelmRelease`s, each with its chart from an `OCIRepository`. It is the
  first HelmRelease-based App Template here. The resources follow the shape
  [giantswarm/appcr-to-helmrelease-converter](https://github.com/giantswarm/appcr-to-helmrelease-converter)
  emits for a migrated App CR, so converted and new apps look alike:
  - the chart version pinned in `spec.ref.tag`
  - values layered through `valuesFrom` like an App CR's: the cluster values
    ConfigMap, the template defaults, then optional `-user-values` (ConfigMap)
    and `-user-secrets` (SOPS-encrypted Secret)
  - upgrades retry 10 times and roll back on failure, 10m timeout; installs
    retry until they succeed, as the cluster chart's default apps do, since
    envoy-gateway and gateway-api-config need CRDs a new cluster only gets with
    its default apps
  - `giantswarm.io/cluster` labels

  `hello-world` is now exposed through an `HTTPRoute` on the `giantswarm-default`
  Gateway as `hello.<cluster base domain>`, instead of an Ingress. The
  `hello_app_cluster` template adds the `hello` subdomain to the Gateway's DNS
  record and certificate. The hostname is built from the
  cluster values, which the hello-world `HelmRelease` lists first in
  `valuesFrom`. The kind test now checks that
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
- Every other workload app in the template is now a `HelmRelease` with its
  chart from an `OCIRepository` as well, in the same shape as the envoy-gateway
  App Template: `hello-world` (App Template, app set and the out-of-band
  examples), `cert-manager-app` and `flux-app`. Only the cluster App CRs
  (`cluster-aws`, from `bases/clusters/capa/template`) still use App Platform.
  Converted from [#153](https://github.com/giantswarm/gitops-template/pull/153).
  - Installs of `cert-manager-app`, `flux-app` and `hello-world` retry 10
    times, as the converter emits for a migrated App CR. `hello-world`'s
    HTTPRoute needs the Gateway API CRDs the envoy-gateway App Template
    installs. Instead of retrying its install forever, every install and
    upgrade of `hello-world` waits until `<cluster>-gateway-api-crds` is ready:
    the `hello_app_cluster` cluster template and the out-of-band examples add
    it to the `HelmRelease`'s `dependsOn`. The App Template leaves it out, so
    it still works in a cluster without envoy-gateway.
    ([#209](https://github.com/giantswarm/gitops-template/issues/209))
  - Values come in the same four `valuesFrom` layers everywhere, the cluster
    values first. App Platform used to add those to an App CR, a `HelmRelease`
    has to list them; `hello-world`'s hostname is built from `baseDomain`.
    Because the user layers are optional, overlays only create the
    `-user-values` ConfigMap; the `patch_app_config.yaml` files that restated
    `valuesFrom` are gone (`kustomize` replaces the list, it cannot append).
  - Release names drop the `<cluster>-` prefix (`hello-world`, `cert-manager`,
    `flux`), as chart-operator named the releases of the App CRs and as
    giantswarm/appcr-to-helmrelease-converter emits them, so a migrated release
    is adopted instead of installed a second time.
  - Kustomize patches that pinned a version through `/spec/version` on an `App`
    now target `spec.ref` on the `OCIRepository`.
  - App CRs could reference a ConfigMap or Secret in another namespace;
    `spec.valuesFrom` cannot. Two example references that pointed at namespaces
    with nothing in them (`org-multi-project`, `hello-world-app`) now resolve
    against the namespace the `HelmRelease` lives in, which is where the
    ConfigMaps were generated all along.

  **Migrating a fork:** delete the old App CRs by hand once their
  `HelmRelease` is ready, `prune: false` keeps them otherwise. While both
  exist, app-operator and helm-controller manage the same release.
- Automatic updates use a `semver` range on the `OCIRepository` instead of
  Flux image automation: dev follows dev builds from `3.0.0` on, staging stable
  releases below `4.0.0`, the out-of-band `hello-world-app-auto` everything from
  `3.0.0-0`. The `$imagepolicy` setters they replace never fired: the markers
  held `${...}` variables, which Flux only substitutes in the cluster, and the
  stage markers sat outside the `ImageUpdateAutomation` update path.
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
- CI: a new commit on a pull request cancels the `validate` run for the commit it replaces, so the kind test no
  longer runs in parallel for the same pull request. Runs for pushes to a branch are not cancelled.
  ([#229](https://github.com/giantswarm/gitops-template/issues/229))

### Removed

- The per-stage `hello_world_app_user_config.yaml` files and the
  `${cluster_name}-hello-world-user-config` ConfigMap the three
  `bases/environments/stages/*/hello_app_cluster/kustomization.yaml` files
  generated from them, plus their `tests/ats` assertions and the parts of
  `docs/add_wc_environments.md` that presented them as the per-stage override
  mechanism for the `hello-web-app` app set. Nothing ever read that ConfigMap:
  the app resolves its values from `${cluster_name}-hello-world-values`, so the
  overrides (`replicaCount: 6` in prod, node pool settings in dev and staging)
  were silently discarded. Two of the three also held cluster chart values
  (`global.nodePools`) rather than app values, so they could not have been wired
  to the app as they stood. Per-app values for the set come from
  `bases/cluster_templates/hello_app_cluster/app_sets/hello-web-app/override_config_hello_world.yaml`,
  which is wired up and documented.
- Every `giantswarm-catalog-oci` `Catalog` CR: the two under the out-of-band
  workload clusters' `mapi/automatic-updates/` and the two under
  `bases/environments/stages/{dev,staging}/hello_app_cluster/automatic_updates/`,
  together with their `tests/ats` assertions. An `OCIRepository` addresses the
  registry directly, so the first pair had nothing left referencing it; the stage
  pair was never referenced by anything in the first place, since the apps in
  those stages resolve from the `giantswarm` catalog. The repository now declares
  no `Catalog` CRs at all.
- The `ImageRepository`, `ImagePolicy` and `ImageUpdateAutomation` objects of
  the dev and staging stages and of the out-of-band `hello-world-app-auto`
  example, with the `automatic_updates/` and `automatic-updates/` directories
  and their `tests/ats` assertions. A `semver` range on the `OCIRepository`
  replaces them, see Changed.
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

- yamllint checks YAML with the rules in `.yamllint.yaml`. An empty `.yamllint` with no rules took precedence, so only
  the syntax was checked. The repository's own YAML is fixed, and `.yamllint.yaml` ignores what can't be edited here:
  SOPS-encrypted `*.enc.yaml` files, devctl's `zz_generated` workflows and the CRD fixtures copied from upstream. GitHub
  Actions' `on:` key passes `truthy`. If your fork relied on the empty `.yamllint`, expect findings when you merge
  this. `tools/fake-flux build` no longer writes empty documents, so `tools/test-all-ff validate` lints the build output
  as it is. ([#217](https://github.com/giantswarm/gitops-template/issues/217))
- Pull requests from forks, which GitHub gives no secrets and a read-only token, get working CI. `validate.yaml` and
  `yaml-diff.yaml` skip their comments there, which they can't post, leave a notice saying why, and put the diff and
  the validation log in the job summary. `tests/ats`
  skips the tests that need the kind cluster with a warning when `GITOPS_MASTER_GPG_KEY` is empty on such a pull
  request, instead of failing with "master gpg key missing"; anywhere else, also in a fork's own runs, a missing key
  still fails it. CI calls `giantswarm/github-workflows` at `0175154`, where the secret is optional and the shared
  workflows skip their comments on such pull requests; its tool defaults are current too.
  ([#225](https://github.com/giantswarm/gitops-template/issues/225), [#228](https://github.com/giantswarm/gitops-template/issues/228))
- The kind test removes the vCluster's temporary `vcluster-values-*.yaml` file even when `helm uninstall` fails, for
  example on a `--wait` timeout. [docs/guides/ci-validation.md](docs/guides/ci-validation.md) now says that a local run
  has to reach kind's Docker network, so it works where Docker runs natively on the host, like the GitHub runner, and
  not where Docker runs in a VM, such as Docker Desktop.
- The notes on the master and `WC_NAME` demo GPG keys in `management-clusters/MC_NAME/.sops.keys` said nothing was
  encrypted with them and that they had no private key; the `FROM_TEMPLATE_WC_NAME` key had no note. Each key now says
  what uses it and where its private key is: CI creates the `sops-gpg-master` Secret from the `GITOPS_MASTER_GPG_KEY`
  secret, and the workload cluster keys are in the `secrets` directory, encrypted with the master key.
- The CAPA cluster base reads the management cluster's values, `global.managementCluster` and
  `global.connectivity.baseDomain`, which `release-aws` requires. Its `HelmRelease` now reads
  `cluster-app-installation-values` (copied into every `org-*` namespace by a Kyverno policy in
  `kyverno-policies-ux` 0.14.0 and newer on Giant Swarm management clusters), then `${cluster_name}-config`.
  `tools/validate-helm-values` and the kind test use a stand-in for `cluster-app-installation-values`.
  `kubectl gs gitops add base` doesn't add the entry; the base's readme describes the difference.
  ([#273](https://github.com/giantswarm/gitops-template/issues/273))
- The kind test's `HelmRelease` check checked nothing: it skipped every `HelmRelease` with a `kubeConfig` or a
  `release-*` chart, which was all 37 of them. It now follows the spec in
  [#219](https://github.com/giantswarm/gitops-template/issues/219). Workload-cluster apps whose kubeconfig Secret
  exists in the test cluster, the six of `out-of-band-no-flux`, have to get `Ready` in the vCluster, and each
  has an assertion of its main workload there. The test creates the cluster's `<cluster>-cluster-values` stand-in,
  and the CRDs, kept in `tests/ats/fixtures/crds`, and the `giantswarm-critical` PriorityClass the apps need in the
  vCluster. For every `HelmRelease`, the chart source, the
  required `valuesFrom` objects and their keys, the kubeconfig Secret and `dependsOn` have to exist, except what the
  management cluster creates for clusters the test doesn't have; a missing one fails before any wait. Every source
  kind now has to get `Ready`, not only `OCIRepository`s. Every `Kustomization` has to get `Ready`, including ones in
  `GITOPS_IGNORED_OBJECTS`, and the test fails when there's none. Assertions find a kind's resource name through API
  discovery. See [docs/guides/ci-validation.md](docs/guides/ci-validation.md#validation-option).
- `tools/test-all-ff validate` now validates Flux and Giant Swarm objects
  against real schemas. kubeconform ran with `-ignore-missing-schemas` and no
  CRD schema source, so it skipped every `HelmRelease`, `OCIRepository` and
  `Kustomization`: 83 of the 139 rendered objects. It now uses the Flux 2.7.5
  CRD schemas (the Flux of `flux-app` 1.12.2 on the management clusters), the
  Kubernetes 1.36.5 schemas instead of `master`, and `giantswarm/json-schema`
  for `Organization`, all pinned. An object whose kind has no schema fails,
  unknown fields fail (`-strict`), and kubeconform errors now fail the job: the
  error flag was set to `true`, which the final numeric check read as 0. The
  `validate` workflow pins kubeconform 0.8.0 instead of the shared workflow's
  default 0.4.13. Closes
  [#216](https://github.com/giantswarm/gitops-template/issues/216).
- The `flux-app` user values of the `WC_NAME_OUT_OF_BAND_FLUX_APP` example set
  the source credentials' `token`, but the chart reads `password`. Its
  template failed with "b64enc: invalid value; expected string". The key is now
  `password`.
- The black pre-commit hook now formats `tests/ats`. Its `exclude: ''` matched
  every path, so black never checked a file. The Python files in `tests/ats`
  are reformatted with it.
- `tools/test-all-ff validate` now exits non-zero when kubeconform reports an
  invalid manifest. The kubeconform failure set the error flag to `true`, which
  the final numeric check read as 0, so only yamllint failures failed the
  `validate` job. The script also runs with `set -u` now.
- `tools/test-all-ff` prints its usage when it is not run from the repository
  root. It called an undefined `usage` function there instead.
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
- The `-direct` out-of-band example `Kustomization` is in the organization namespace, next to the kubeconfig Secret,
  but referenced the `GitRepository` without a namespace, so Flux looked for it there and never reconciled the
  example. Its `sourceRef` now sets `namespace: default`, as `docs/add_wc_structure.md` already showed. The kind test
  found this once it reconciled the example ([#224](https://github.com/giantswarm/gitops-template/issues/224)).
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
- CI: `validate.yaml` listed a `HEAD_BRANCH` placeholder among its push branches. It matched no branch and was
  documented nowhere; the push trigger now lists `main` only.
  ([#230](https://github.com/giantswarm/gitops-template/issues/230))
- `tests/ats` compares a `values` key in the assertions with the object in the cluster. The comparison skipped a
  changed `values` whenever DeepDiff printed no line diff for it, which covers every single-line value (such as a
  Secret's base64 `values`) and every other change under the same top-level key, so a values regression passed. Only
  trailing whitespace on each line is ignored now, which is what the skip was for: `|` against `|-` in an assertion
  file. ([#222](https://github.com/giantswarm/gitops-template/issues/222))

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
