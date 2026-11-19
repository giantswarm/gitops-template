# Configuring extra validation and diff previews on GitHub

With this repository, we're also including a GitHub workflow, that can make your work with this
repo easier. It is available in the [validate.yaml](../../.github/workflows/validate.yaml) file.

`validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call shared workflows from
[giantswarm/github-workflows](https://github.com/giantswarm/github-workflows) at a commit SHA, followed by a `# main`
comment, so a change there doesn't change your CI until you take it. With Renovate and the `renovate.json5` this
repository ships, Renovate opens a pull request that moves the SHA to the newest commit on `main` and merges it once
your checks pass. Without Renovate, move the SHA yourself when you want a fix from upstream.

The workflow offers the following jobs:

- `check_pre_commit`: it runs all the `pre-commit` validation checks, including
  [check-kustomization-paths](#check-kustomization-paths),
- `validate`: templates all your `Kustomizations` available in `workload_clusters` and passes the output
  through a YAML and Kubernetes objects linters to make sure that your code is valid YAML and produces final
  manifests understandable to Kubernetes. It also renders the chart of every `HelmRelease` with its merged values
  (see [validate-helm-values](../../tools/README.md#validate-helm-values)), so values the chart's schema rejects fail
  the job. A variable that a `Kustomization`'s manifests use but its `spec.postBuild.substitute` doesn't set fails the
  job, where Flux would replace it with an empty string. `flux build` doesn't read `spec.postBuild.substituteFrom`, so
  a variable set only there fails the job too, although Flux sets it on the cluster. It reads each `Kustomization` as
  Flux applies it, from the build of the directories above its file that have a `kustomization.yaml`, such as the
  organisation's, which sets `organization` and the organisation's namespace, see
  [fake-flux](../../tools/README.md#fake-flux). It attaches a validation report as a comment to your PR.
- `get_diff`: it templates your changed manifests and compares them to a templated version without your changes,
  then it generates and saves a diff between the two and attaches it to your PR
- `test on kind`: deploys a full `flux` installation to a test `kind` cluster, then deploys your `Kustomizations`
  there to verify if they are deployed fine. It checks if all the `Kustomizations` are reconciled as expected
  and additionally if all the statements present in `tests/ats/assertions` are also available in objects in the
  cluster.
  Its last test, `test_prune`, checks pruning on the `out-of-band-no-flux` cluster. It leaves the organisation's
  `ORG_NAME.yaml` out of the `GitRepository` with `spec.ignore`, and drops an App Set from what the cluster's apps
  `Kustomization` builds with `$patch: delete` patches in its `spec.patches`, as `app_sets/kustomization.yaml` lists
  the App Set and `spec.ignore` can't change that list. The App Set has to go. The organisation's `kustomization.yaml`
  takes the organisation's name from the `Organization`, so without `ORG_NAME.yaml` the management cluster's
  `Kustomization`, `mc-name-gitops`, has to report that its build failed and prune nothing: its inventory keeps the
  `Organization` and the cluster's `Kustomization`s, and they stay. Then it deletes the cluster's two
  `Kustomization`s. Everything they applied has to go, and the cluster's `HelmRelease` has to stay. It deletes what
  the other tests check, so it runs last and fails if they didn't run before it.

You can check a demo PR where this is used in [PR 44](https://github.com/giantswarm/gitops-template/pull/44).

## check-kustomization-paths

[tools/check-kustomization-paths](../../tools/check-kustomization-paths) runs as a `pre-commit` hook. For every Flux
`Kustomization` (`kustomize.toolkit.fluxcd.io/v1`, or the older `v1beta2`) that applies this repository, outside of
`tools/testdata`, it checks that `spec.path` exists and builds. This repository's `GitRepository` is the `sourceRef` of
the management cluster's own `Kustomization`, the one whose path is the directory of its file, such as
`MC_NAME.yaml`. A `Kustomization` with another source reads another repository, so it's left out. The hook builds a
path that has a `kustomization.yaml`, `kustomization.yml` or `Kustomization` with `kustomize build`, or with
`kubectl kustomize` if `kustomize` isn't installed. A path without one it builds the way Flux does, from the YAML files
and the directories with a kustomization file below it, and such a path must not be empty. It fails when it finds no
`Kustomization`, no management cluster `Kustomization` or when `yq` can't read them, rather than pass without
checking anything. Otherwise it fails, naming the `Kustomization`, its file and its path, when:

- the path doesn't exist: restore the directory, or delete the `Kustomization`, its file and its entry in the
  `kustomization.yaml` that lists it;
- the path is empty: delete the `Kustomization` the same way;
- a `kustomization.yaml` lists something that's gone, for example the `app_sets/` of a cluster whose last App Set you
  removed: remove the entry, or restore what it names.

On a cluster, each of these stops Flux applying the `Kustomization` until it's fixed, and it doesn't delete what the
`Kustomization` applied before. `tools/test-all-ff validate` checks that the hook fails on the fixture in
`tools/testdata/gone-path`, leaving out its `Kustomization` with another source, and on a directory without any
`Kustomization`.

## When the workflow runs

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

A pull request that changes only Markdown files (`*.md`, anywhere in the repository, `CHANGELOG.md` included) skips
`validate` and the kind test, as Markdown changes nothing they check. Its first job, `changes`, lists the files the
pull request changes; a file renamed from or to another type counts as a change to that type too. Instead of the shared
workflow, `validate.yaml` then calls [validate-markdown.yaml](../../.github/workflows/validate-markdown.yaml), which
runs the same `pre-commit` hooks, so the Markdown is still linted, and reports `validate / validate` and
`validate / test_on_kind` as skipped. GitHub counts a skipped check as passed, so a branch that requires these checks
doesn't wait for them. Any other file in the pull request, and every push to `main`, runs everything.

A pull request from a fork gets a read-only token and none of the repository's secrets. `yaml-diff.yaml` and
`validate.yaml` skip their comments there, which they can't post, leave a notice on the run saying why, and put the
diff and the validation log in the job summary. The kind test skips the tests that need
the cluster there; see [`GITOPS_MASTER_GPG_KEY`](#configuration).

## `test-on-kind` validation step - additional information

This validation step offers some broader possibilities for validation, but also requires extra configuration.

### Validation option

Every example is something you build from, so an example the test can reconcile has to get `Ready`. The test installs
what an example needs; it doesn't skip examples to pass. Creating clusters is the one exception, as the test can't
do it (see [Cluster API](#cluster-api)).

The objects named in `GITOPS_IGNORED_OBJECTS` that are `HelmRelease`s or sources aren't looked at at all. The list
doesn't apply to `Kustomization`s. The test checks:

| Objects | Check |
| --- | --- |
| `Kustomization`s | All of them get `Ready`, including the ones `GITOPS_IGNORED_OBJECTS` names. The test lists them again after each wait, as the root `Kustomization`s create the cluster ones, until no new one appears. Without any `Kustomization`, the test fails. |
| Sources: `OCIRepository`s, `GitRepository`s, `HelmRepository`s, `HelmChart`s and `Bucket`s | All of them get `Ready`. An OCI `HelmRepository` has no `Ready` condition, as Flux doesn't reconcile it, so it only has to exist. If there are none of a kind, the test passes and logs it. |
| `HelmRelease`s | Their references exist, and the ones the test cluster can run get `Ready`, see below. If there are none, the test passes and logs it. |

An object is `Ready` when its first condition, where Flux keeps `Ready`, is `Ready` and `True`. Each check waits
until every object it waits for has been `Ready` once; none of them makes a final pass over all the objects
afterwards. The waits are 60 seconds for each round of `Kustomization`s, 180 seconds for each kind of source and 720
seconds for `HelmRelease`s, longer than the examples' `timeout` of 10 minutes, so a `HelmRelease` that doesn't get ready
reports helm-controller's reason. The test reports the first condition of each object that isn't `Ready`.

Each `HelmRelease` is one of these kinds:

| Kind | Waited for until `Ready` | References checked |
| --- | --- | --- |
| Runs on the management cluster: no `kubeConfig`, and not a cluster chart | Yes | All |
| Cluster chart: exactly `release-aws`, `release-azure`, `release-vsphere` or `release-cloud-director` | No: the test has no cloud account to create the cluster in | All |
| Workload-cluster app whose `spec.kubeConfig.secretRef` Secret exists in the test cluster | Yes | All |
| Workload-cluster app whose Secret doesn't exist | No | All, except the two the management cluster creates |
| One of the first and third kinds, whose `dependsOn` chain reaches a `HelmRelease` of the second or fourth kind, or an ignored one, or whose chart source is ignored | No | All |

The test tells the two kinds of workload-cluster apps apart only by whether the kubeconfig Secret exists, never by the
cluster's name. The references it checks exist; it doesn't read what's in them:

- the chart source, the `chartRef` or the `chart.spec.sourceRef`, unless it's ignored. Whether it's `Ready` is the
  source check above.
- every `valuesFrom` object that isn't `optional: true`, and its key. The values are validated by
  [validate-helm-values](../../tools/README.md#validate-helm-values) instead.
- the `kubeConfig` Secret.
- every `HelmRelease` in `dependsOn`.

The references are checked before the test waits for any `HelmRelease`, so a missing one fails the test at once.

For a workload-cluster app whose Secret doesn't exist, two references are exempt, by exact name: a kubeconfig Secret
named `<cluster>-kubeconfig`, and the `<cluster>-cluster-values` ConfigMap in its `valuesFrom`. The management cluster
creates both.

Additionally, every file present in `tests/ats/assertions/exists` is loaded and verified. Each of these files
has to contain one or more YAML description of objects of Kubernetes objects you expect to be present in the cluster
after your Kustomizations are deployed. Each object has to have `kind:`, `metadata.name` and `metadata.namespace`
(if it's a namespace-scoped object) defined. The rest of object definition is arbitrary, but every property specified
in the assertions file must be also present (and have exactly the same value) as the property of the object present
in cluster. Strings are compared as text, so a ConfigMap's `values` has to match line by line. Only trailing whitespace
is ignored: whether the assertion writes a block as `|` or `|-`, or a line ends in a space, doesn't matter.

A cluster's node pools come from several ConfigMaps in the `valuesFrom` of its `HelmRelease`, so no single assertion
shows them. For every `HelmRelease` that creates a workload cluster, the test reads the `HelmRelease` and its
ConfigMaps from the test cluster, merges the values the way helm-controller does, `spec.values` included, and compares
the node pools with `EXPECTED_NODE_POOLS` in [node_pools.py](../../tests/ats/node_pools.py). A production cluster gets
the stage's `nodepool0` and its region's extra pool. Dev and staging have no pools of their own and get the chart's
defaults. The test fails for a workload cluster that isn't in `EXPECTED_NODE_POOLS`, so when you add a cluster or
change its node pools, update that table.

### Versions

The test cluster runs the same versions as a Giant Swarm management cluster where it can:

| Component | Version | Set in |
| --- | --- | --- |
| Kubernetes | v1.36.1, the default node image of kind v0.32.0 | `kind_ver` in [validate.yaml](../../.github/workflows/validate.yaml) |
| flux-app | 1.12.2 (Flux v2.7.5) | `gitops_flux_app_version` in validate.yaml |
| Cluster API CRDs | v1.14.4 | `CAPI_VERSION` in [conftest.py](../../tests/ats/conftest.py) |

The test installs Flux with helm, from Giant Swarm's `flux-app` chart in `oci://gsoci.azurecr.io/charts/giantswarm`.
It doesn't install the app platform (app-operator and chart-operator), as the template uses no `App` CRs.
[tests/ats/fixtures/flux-app-values.yaml](../../tests/ats/fixtures/flux-app-values.yaml) turns off the objects whose
CRDs the kind cluster doesn't have: the `PodMonitor`s, and the chart's kube-state-metrics with its `ServiceMonitor`
and `CiliumNetworkPolicy`. The shared workflow still installs `apptestctl`, at its own default version, but nothing
uses it.

The shared workflow doesn't take a node image, so the Kubernetes patch version is whatever the kind release defaults
to. pytest prints the version it ran against at the top of its output, as `kubernetes server: v1.36.1 (linux/amd64)`.

### Cluster API

This repository doesn't test cluster creation. Workload clusters are created by the `release-aws` chart on a real
management cluster, which a kind cluster can't stand in for.

The test cluster has the Cluster API core CRDs only: the `CustomResourceDefinition`s from the `core-components.yaml`
of the Cluster API release, in the `cluster.x-k8s.io` group and its `addons`, `ipam` and `runtime` subgroups. It runs no
Cluster API controllers and no infrastructure providers such as CAPA or CAPZ, so nothing acts on a Cluster API object.
A test can create one, for example a stand-in `Cluster`, and set its status itself. Use `v1beta2`, the version the
objects are stored in: the CRDs are installed without their conversion webhook, so other versions are served without
conversion.

The test does that for every cluster whose apps wait for it, as listed in `GATES` in
[cluster_gates.py](../../tests/ats/cluster_gates.py). It creates a paused stand-in `Cluster` with `Available` `False`.
The cluster's `Kustomization` still has to apply the base apps, while the apps `Kustomization` has to report
`DependencyNotReady` without applying anything. Then it sets `Available` to `True`, and the apps `Kustomization` has to
get `Ready`. `test_apps_wait_for_cluster` reports the result. The other checks run after it, as the cluster
`Kustomization`s only get `Ready` once their `Cluster` is `Available`. When you add a cluster with apps, add it to
`GATES`: a test without the cluster compares the list with the `Kustomization`s in the repository.

The shared workflow still installs `clusterctl`, at its own default version, but nothing uses it.

### Configuration

This build step requires additional configuration using the following environment variables:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  version provided by Giant Swarm
- `GITOPS_INIT_NAMESPACES`: namespaces used for testing need to be initialized (RBAC permissions) before
  they can be used; as such this variable needs to hold a comma separated list of namespaces, where you want
  to deploy `Kustomization` objects during the test (example: `default,org-org-name`)
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) `HelmRelease`s and sources that the test doesn't
  look at (example: "org-org-name/my-helmrelease"). It doesn't apply to `Kustomization`s, which all have to get
  `Ready`. [validate.yaml](../../.github/workflows/validate.yaml) sets it with the `gitops_ignored_objects` input of
  the shared workflow, empty in this repository. Keep it empty: an example the test can reconcile has to get `Ready`,
  so install what it needs in the test instead.
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. It is recommended
  to set it as a repository secret on github (tho job is configured to pick up this secret by default).
  An empty key fails the test, also in a fork's own runs, with one exception: on a pull request from a fork, which
  GitHub gives no secrets, the test skips every test that needs the cluster and says so in a warning on the run; the
  checks that need no cluster still run.

### The workload cluster of the `out-of-band-no-flux` example

`WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload cluster, and the cluster's
`HelmRelease`s install their apps there, through the `out-of-band-no-flux-kubeconfig` Secret a management cluster
has for it. The test installs a [vCluster](https://www.vcluster.com/) named `out-of-band-no-flux` in the test
cluster and puts its kubeconfig, with the vCluster's in-cluster Service as the server, in that Secret, so the
`Kustomization` and the `HelmRelease`s reconcile like on a management cluster. As that Secret exists, the apps have to
get `Ready`. The test also creates what they need:

- the `out-of-band-no-flux-cluster-values` ConfigMap, which a management cluster creates for every workload
  cluster. Its values are [tools/values-stubs/cluster-values.yaml](../../tools/values-stubs/cluster-values.yaml).
- in the vCluster, the CRDs that a Giant Swarm workload cluster gets from its default apps and the apps create objects
  of: Cilium's `CiliumNetworkPolicy`, `PodMonitor`, Grafana's `PodLogs`, cert-manager's `Certificate` and `Issuer`,
  Kyverno's `ClusterPolicy` and external-dns' `DNSEndpoint`. Only the CRDs: nothing in the test needs their
  controllers. They're kept in [tests/ats/fixtures/crds](../../tests/ats/fixtures/crds/README.md), which says where
  each comes from, so the test doesn't download them.
- in the vCluster, the `giantswarm-critical` PriorityClass, which the cluster chart creates in every Giant Swarm
  workload cluster. The `envoy-gateway` Deployment's pods can't be created without it.
- in the vCluster, Flux's `GitRepository` and `Kustomization` CRDs, copied from the test cluster, where flux-app
  installed them. The `-direct` Kustomization delivers the `GitRepository` and `Kustomization` of the
  [application team](./app-teams.md) `hello-team-wc`, whose Flux runs in the workload cluster. The vCluster runs no
  Flux: the objects only have to exist.

The vCluster runs CoreDNS, as the apps run pods there.

Every file in `tests/ats/assertions/exists-in-workload-cluster` is verified against the vCluster, the same way as the
files in `tests/ats/assertions/exists`. They list the main workload of each app:

- Every workload-cluster app whose kubeconfig Secret exists needs an assertion of its main workload: an object with a
  `helmRelease: <namespace>/<name>` key naming the `HelmRelease`. The key isn't a field of the object, so the
  comparison skips it. The test fails for a `HelmRelease` without one, so a new app needs an assertion. For
  `gateway-api-crds`, which runs no workload, it's the `gateways.gateway.networking.k8s.io` CRD the chart installs.
- Every `Deployment` in them has to be available, too. That includes the `podinfo` `Deployment` that the
  [application team](./app-teams.md) `hello-team` delivers from its own repository into its namespace. Its
  `Kustomization` runs as the `automation` ServiceAccount, which the test creates in every namespace of
  `GITOPS_INIT_NAMESPACES`, `org-org-name` among them, as a Giant Swarm management cluster has it.
- The `GitRepository` and `Kustomization` of the application team `hello-team-wc` only have to exist, as nothing in
  the vCluster reconciles them.
- The `giantswarm-default` `Gateway` of the `gateway-api-config` app only has to exist. kind has no load balancer for
  its Service, so the `Gateway` can't be `Programmed`. Its `HelmRelease` gets `Ready` all the same.

Running the test locally needs `helm` in your `$PATH`. pytest reaches the vCluster at the kind node's IP address,
on a node port of the vCluster's Service, so it has to run where it can route to kind's Docker network: where Docker
runs natively on the host, like the GitHub runner. Where Docker runs in a VM, such as Docker Desktop or a Podman
machine, or where pytest runs in a container outside that network, the setup of the vCluster times out.

`tests/ats/conftest.py` pins the `vcluster` chart (`VCLUSTER_CHART_VERSION`, 0.37.6) and the vCluster's Kubernetes
image (`VCLUSTER_KUBERNETES_IMAGE_TAG`, v1.36.6). Keep the image on the Kubernetes minor version of the kind cluster and
the management clusters when you bump either. A vCluster runs as a pod in the kind cluster, so more workload clusters
cost a pod each rather than another kind cluster on the runner. In a [comparison](https://github.com/giantswarm/gitops-template/pull/277)
with a second kind cluster, the vCluster took 29 seconds to set up against 17 (medians of 6 and 15 runs), and the whole
kind job 254 seconds against 237, less than the spread of about 60 seconds between runs of the same setup.

### Kyverno

The [shared-objects example](../add_mc.md#share-an-object-with-every-organization) is a Kyverno `ClusterPolicy`, so
the test installs Kyverno before Flux applies the repository. It installs Giant Swarm's charts, the ones team Shield
ships to the management clusters, from `oci://gsoci.azurecr.io/charts/giantswarm`: `kyverno-crds` 1.19.2, as the
`kyverno` chart leaves the CRDs to it, then `kyverno` 0.26.1, the chart of `kyverno-app`. Kyverno's pods use the
`giantswarm-critical` PriorityClass and its `PolicyException`s go in the `giantswarm` namespace, which every management
cluster has, so the test first installs Giant Swarm's `priority-classes` 0.3.1 chart and creates the namespace. The
charts are pinned in `tests/ats/kyverno_install.py`. [tests/ats/fixtures/kyverno-values.yaml](../../tests/ats/fixtures/kyverno-values.yaml)
turns off the objects whose CRDs the kind cluster doesn't have: the `CiliumNetworkPolicy`s, `PodLogs`,
`VerticalPodAutoscaler`s and `ServiceMonitor`s. It also lowers the background and reports controllers' requests from
the chart's 500m CPU and 1Gi, sized for a management cluster, so that Flux still fits on the single kind node.
`test_shared_object_copied` creates a new `org-*` namespace and waits for the `shared-ca-bundle` ConfigMap to be
copied into it. It then changes the source, with the management cluster's
`Kustomization` suspended, waits for the copy to follow, and puts the source back.

### Chainsaw tests

Next to the pytest checks, [tests/chainsaw](../../tests/chainsaw) holds tests written in YAML for
[Chainsaw](https://kyverno.github.io/chainsaw/). Each one is a `chainsaw-test.yaml` with steps that wait for an object
to match what the step expects, such as its `Ready` condition:

| Test | What it checks |
| --- | --- |
| `readiness-ordering` | Along the `out-of-band-no-flux` cluster's chain, each object is linked to the one before it and is `Ready`: the `Cluster` is `Available`, the cluster's `Kustomization` health-checks it and waits for it to be `Available`, the apps `Kustomization` depends on that one, and the `hello-world-standalone` `HelmRelease` depends on `gateway-api-crds`. The test checks the links and the state the objects end in, not the order they got `Ready` in. A failure names the first object of the chain that isn't `Ready` or isn't linked. |
| `kyverno-generate` | The [shared-objects](../add_mc.md#share-an-object-with-every-organization) policy is `Ready`, and the organization namespace has its copy of the ConfigMap, with the source's data and Kyverno's labels. That a new organization gets a copy, and that a change to the source reaches the copies, `test_shared_object_copied` checks in the kind test. |
| `external-secrets` | The [External Secrets Operator example](../getting-started.md#4-deploy-an-app)'s `ExternalSecret` has synced, the Secret it writes has the `reconcile.fluxcd.io/watch` label and the values, and the `HelmRelease` that reads it is `Ready`. |

The steps name no objects themselves: they read the names from
[tests/chainsaw/values.yaml](../../tests/chainsaw/values.yaml), which names the template's examples. The shared
workflow runs only pytest on the kind cluster, so `test_chainsaw` in
[test_flux_objects.py](../../tests/ats/test_flux_objects.py) runs Chainsaw, once the stand-in clusters exist and the
`HelmRelease`s are `Ready`. It logs Chainsaw's report, and fails when a Chainsaw test fails, naming the step that
failed.
It downloads the Chainsaw release that `CHAINSAW_VERSION` in [tests/ats/chainsaw.py](../../tests/ats/chainsaw.py) pins
and checks it against `CHAINSAW_SHA256`. Renovate moves the version but not the checksum: set the checksum of the new
release's `chainsaw_linux_amd64.tar.gz`, from its `checksums.txt`, in the same pull request.

To add a test, create a directory in `tests/chainsaw` with a `chainsaw-test.yaml`, and put the names it needs in
`values.yaml`.

#### Run them against a management cluster

The tests only read objects. Chainsaw itself creates a `chainsaw-*` namespace for each test and deletes it again. So
you can run them on demand against a management cluster that Flux reconciles from your repository, for example after
a change, to check that it got `Ready` there:

1. Install [Chainsaw](https://kyverno.github.io/chainsaw/latest/quick-start/install/), the version in
   `tests/ats/chainsaw.py`.
2. Copy `tests/chainsaw/values.yaml` and set the names of your own objects: your organization namespace, your
   cluster, its `Kustomization`s and `HelmRelease`s, your `ExternalSecret` and your shared object. Run only the tests
   whose examples you use.
3. With your kubeconfig's context on the management cluster, run:

   ```sh
   chainsaw test --test-dir tests/chainsaw --values my-values.yaml
   ```

   Add `--include-test-regex 'readiness-ordering|external-secrets'` to run some of the tests only.

Your user needs to read the objects the tests check, and to create and delete Chainsaw's namespaces.

## Superseded runs

The kind test takes a while, so `validate.yaml` runs once per pull request at a time. When you push a new commit to
a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
cancel the run in progress: it finishes, and GitHub keeps only the newest of the push runs waiting behind it.
