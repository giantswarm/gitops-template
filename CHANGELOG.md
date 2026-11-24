# Changelog

Based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
following [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

This release rebuilds the template: its layout, its examples, its tests and its documentation. The repository is now
at [structure version](docs/reference/repo-structure.md#structure-version) 3, the layout kubectl-gs X.Y.Z and newer
write. Clusters and apps are Flux `HelmRelease`s from Giant Swarm's charts on `gsoci.azurecr.io`, and every example
gets `Ready` in CI. To bring an existing fork up to date, follow
[Bring an older fork up to date](docs/how-to/upgrade-fork.md), which says what each step changes on a running
management cluster.

**Breaking changes.** A fork has to make these changes, listed under
[What's mandatory](docs/how-to/upgrade-fork.md#whats-mandatory):

- Update kubectl-gs to X.Y.Z or newer. Older releases write structure version 2, with a `mapi` directory.
- Move to structure version 3 with `kubectl gs gitops upgrade`: workload clusters lose their `mapi` directory, and
  each organisation gets a `namespace.yaml` and a `namespace` directory.
- Move the workload cluster `Kustomization`s and their SOPS keys from `default` into the organisation's namespace,
  `org-<name>`. kubectl-gs X.Y.Z refuses to add a cluster or a cluster key to an organisation that hasn't.
- Give every cluster its region, as a kustomize Component from `bases/environments/regions`. Without one, `release-aws`
  takes the region of the management cluster.

The examples changed in these ways as well. A fork can follow one at a time, each in its own pull request:

- The `Kustomization`s have `prune: true` instead of `prune: false`, so deleting an app's files uninstalls the app.
- Apps install into a namespace of their own in the workload cluster, such as `hello-world`, instead of `org-<name>`.
  Moving an installed app reinstalls it.
- There are no `App` custom resources, and `kubectl gs gitops upgrade` fails on any it finds.
  [Adopt an app that's already installed](docs/how-to/adopt-app.md) moves one to a `HelmRelease` without reinstalling
  it.
- `bases/cluster_templates` and `bases/app_sets` are replaced by cluster bases in `bases/clusters` and stacks in
  `bases/stacks`. The CAPA base moves from `bases/clusters/capa/template` to `bases/clusters/capa`, envoy-gateway from
  `bases/apps` to `bases/stacks`, and the stages in `bases/environments` are kustomize Components.
- File and resource names follow what `kubectl gs gitops` writes, such as `helm-release.yaml`, `oci-repository.yaml`
  and the `${cluster_name}-cluster-userconfig` ConfigMap. Only the ConfigMap's new name shows on the cluster.

### Added

Layout and Flux:

- `.gitops-metadata.yaml` records the structure version, so `kubectl gs gitops check` can tell a fork that it has
  fallen behind. See [Structure version](docs/reference/repo-structure.md#structure-version).
- A chain of Flux `Kustomization`s: `MC_NAME.yaml` applies only `Organization`s and objects in `default`, each
  organisation's `namespace.yaml` applies its namespace, and each cluster has a cluster and an apps `Kustomization`
  there, all as the organisation's `automation` ServiceAccount. See
  [Flux `Kustomization`s](docs/reference/repo-structure.md#flux-kustomizations).
- A cluster's apps install once Cluster API reports its control plane available and reachable, not before, and one
  short node pool no longer holds back changes to the apps.
- The organisation's name is set once, in its `Organization`, and kustomize `replacements` copy it everywhere else. See
  [The organisation's name](docs/reference/repo-structure.md#the-organisations-name).
- Deletion protection: the objects whose deletion would delete a cluster, an organisation or a key carry the
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the `giantswarm.io/prevent-deletion` label. See
  [Deletion protection](docs/explanation/deletion-protection.md).
- Values ConfigMaps and Secrets carry `reconcile.fluxcd.io/watch: Enabled`, so a change to values applies at once.
  `Kustomization`s reconcile every 10 minutes and retry after one.

Clusters and apps:

- The CAPA cluster base in [bases/clusters/capa](bases/clusters/capa/readme.md) installs the `release-aws` chart from an
  `OCIRepository`, with the Giant Swarm release as its tag. It reads the management cluster's
  `cluster-app-installation-values` first and doesn't retry a failed install, which would delete the cluster.
- A cluster's own values, from a ConfigMap and a patch beside the base, and the order of every `valuesFrom` layer. See
  [Give one cluster its own values](docs/how-to/cluster-values.md) and [Values](docs/reference/values.md).
- App Templates in `bases/apps`, stacks in `bases/stacks`, and stages and regions in `bases/environments`, each with a
  tutorial under [docs/tutorials/intermediate](docs/README.md#intermediate).
- The stages promote app and release versions from dev to staging to prod, with Renovate opening one pull request per
  stage.
- Automatic updates through a `semver` range on the app's `OCIRepository`. See
  [Automatic updates](docs/tutorials/intermediate/automatic-updates.md).
- Multicluster apps: a Flux Operator `ResourceSet` in an organisation's `multicluster/apps` installs an app on every
  cluster in `clusters.yaml`. See [Multicluster apps](docs/tutorials/advanced/multicluster-apps.md).
- Scheduled upgrades: a `ResourceSetInputProvider` holds an app's or a cluster's release upgrades until an upgrade
  window, as in the `WC_NAME_SCHEDULED_UPGRADES` example. See
  [Scheduled upgrades](docs/tutorials/advanced/scheduled-upgrades.md) and
  [Move a running cluster to scheduled upgrades](docs/how-to/scheduled-upgrades-existing-cluster.md).
- Out-of-band delivery both ways: the management cluster pushes `out-of-band/` through a `-direct` `Kustomization` with
  the cluster's kubeconfig, or Flux in the workload cluster pulls it. See
  [Out-of-band resources](docs/tutorials/advanced/out-of-band.md).
- Application teams: a team keeps its own repository, which a Flux `Kustomization` in its cluster's `teams` directory
  applies to the workload cluster. See [Application teams](docs/tutorials/advanced/teams.md).
- The Envoy Gateway stack in [bases/stacks/envoy-gateway](bases/stacks/envoy-gateway/README.md) installs the Gateway
  API CRDs, Envoy Gateway and its configuration in order. hello-world answers at `hello.<cluster base domain>` through
  an `HTTPRoute`, and the basic tutorial ends on its page.
- Objects every organisation shares, from a kustomize base in `bases/shared_objects`. See
  [Give every organisation the same object](docs/how-to/share-objects.md).
- Commit statuses: each `Kustomization` reports on the GitHub commit it applied, from the management cluster's and each
  organisation's `notifications`. See [Report reconcile status on GitHub commits](docs/how-to/commit-statuses.md).

Secrets:

- SOPS with a key per workload cluster, GPG or age, next to the master key. See
  [Keep secrets in the repository](docs/how-to/sops.md) and [SOPS keys](docs/reference/sops-keys.md).
- External Secrets Operator next to SOPS, with namespaced `SecretStore`s for AWS Secrets Manager and Azure Key Vault in
  `bases/secret_stores`. See [External Secrets Operator](docs/how-to/external-secrets.md) and
  [Secrets](docs/explanation/secrets.md).
- A Kyverno `Policy` in each organisation's `multicluster/secret-stores` generates a `SecretStore` for every workload
  cluster as it comes up, so ESO can push secrets, including a generated password, into a new cluster. See
  [Put secrets into new workload clusters](docs/how-to/workload-cluster-secrets.md).
- Secrets go into the repository encrypted on their way in, never in plain text, and the `check-sops-encrypted`
  pre-commit hook refuses a `*.enc.yaml` file that isn't encrypted.

Documentation:

- The documentation is rewritten in four kinds, indexed in [docs/README.md](docs/README.md): tutorials in three tiers
  (basic, intermediate, advanced), how-to guides, reference and explanation. The pages under `docs/` and `docs/guides`
  that they replace link to their new places.
- How-to guides for troubleshooting and recovery, adding, changing and adopting apps, deleting a cluster, kubectl-gs,
  another provider's cluster base, running the template on Azure, vSphere or Cloud Director, checking a change,
  configuring CI in a fork and upgrading a fork.
- [One owner per object](docs/explanation/one-owner.md) explains why two reconcilers must never manage one object, and
  [When something isn't Ready](docs/how-to/troubleshooting.md) how to find which Flux object applied a resource.
- Every example directory under `bases/` and `management-clusters/` has a README saying what it shows and what to change
  when you copy it.
- [Voice](docs/contributing/voice.md) sets how the documentation is written. [AGENTS.md](AGENTS.md) and the
  [`giantswarm-gitops` skill](.agents/skills/giantswarm-gitops/SKILL.md) tell coding agents how the platform and this
  repository work, in the template and in a fork.

Tools and CI:

- `tools/validate-helm-values` renders the chart of every `HelmRelease` with its merged values against the chart's
  schema, and `tools/test-all-ff validate` checks objects against pinned Kubernetes, Flux and Giant Swarm schemas and
  fails on a variable a `Kustomization` doesn't set. See [tools/README.md](tools/README.md).
- Pre-commit hooks `check-kustomization-paths`, `check-directory-readmes` and `check-sops-encrypted`. See
  [Check a change before you push](docs/how-to/check-changes.md).
- The kind test runs in a fork as it is: it finds each management cluster's root `Kustomization` in the repository,
  and [tests/ats/kind-test.yaml](tests/ats/kind-test.yaml) binds the example checks to the examples, skipping those a
  fork has deleted. See [Configure CI in a fork](docs/how-to/configure-ci.md).
- The kind test gives `automation` the rights it has on a management cluster, enforces the platform's admission
  policies for Flux and Flux Operator objects, reconciles the out-of-band examples in a vCluster, checks pruning, and
  fails when two `Kustomization`s apply one object.
- Tests in `tests/ats` that need no cluster, and path-based CI: a pull request that changes nothing the tests read gets
  a light run of pre-commit and those tests instead of the kind test. See [CI checks](docs/reference/ci-checks.md).
- Chainsaw tests in `tests/chainsaw` for a real management cluster, run by hand. See
  [Testing the repository](docs/tutorials/advanced/testing.md).
- The `yaml-diff` workflow comments a semantic diff of the YAML a pull request changes, without key order.
- [renovate.json5](renovate.json5) extends Giant Swarm's shared preset and updates chart tags, the Giant Swarm release,
  the versions CI pins and the pre-commit hooks. It never automerges a release update, as that rolls the nodes, and it
  holds the pins that stand for the management clusters at the versions they run.

### Changed

- The template is written for, and CI tests against, what a Giant Swarm management cluster runs: Kubernetes 1.36,
  Flux 2.7.5 (`flux-app` 1.12.2), Flux Operator v0.62.1, External Secrets Operator 2.14, Kyverno from `kyverno` 0.26.2
  with `kyverno-policies-ux` 0.16.0 for deletion protection, and Cluster API v1.14.4, with clusters at
  `cluster.x-k8s.io/v1beta2`.
- The kind test installs Flux with helm and no longer installs the App Platform. It installs Kyverno, External Secrets
  Operator and Flux Operator from Giant Swarm's charts, and the Cluster API CRDs only.
- CI calls the shared `gitops-validate` workflow of `giantswarm/github-workflows`, pinned to a commit SHA, and works
  on pull requests from forks.
- The example clusters' names fit `release-aws`'s 20-character limit, such as `hello-app-prod-usw`.

### Removed

- The `mapi` directory of every workload cluster.
- `bases/cluster_templates`, `bases/app_sets` and `bases/clusters/capa/template`.
- Every `App` and `Catalog` custom resource, Flux image automation (`ImageRepository`, `ImagePolicy`,
  `ImageUpdateAutomation`), ingress-nginx and the `simple-db-app` demo, whose chart is published nowhere.
- The alphabetical `key-ordering` rule of yamllint.

### Fixed

- Examples that couldn't get `Ready`: cluster names too long for `release-aws`, a cluster base that didn't read the
  installation values, and a pulled out-of-band ConfigMap with an invalid name.
- The hello-world examples rendered the chart's default nginx `Ingress`. They now have an `HTTPRoute`, and wait for the
  Gateway API CRDs with `dependsOn` instead of retrying their install forever.
- The docs read secrets through namespaced `SecretStore`s instead of a `ClusterSecretStore`, which a customer can't
  create on a management cluster.
- Uninstalling the envoy-gateway stack no longer waits on the `GatewayClass` finalizer until it times out.
- yamllint uses the rules in `.yamllint.yaml`, `tools/test-all-ff validate` fails on `kubeconform` errors, and the kind
  test's `HelmRelease` check checks the `HelmRelease`s.

## [0.1.0] Initial release

- Added
  - ability to test on `kind` cluster and evaluate expectations
  - description and examples for environment management
  - initial release with basic functionality and docs in place

## [Unreleased]
