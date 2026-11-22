# CI checks

This page says what each CI job and test checks, and why. To set the workflows up in a fork, see
[Configure CI](../how-to/configure-ci.md). To run the same checks before you push, see
[Check a change before you push](../how-to/check-changes.md). To run the kind test on your machine or to test a
management cluster with Chainsaw, see [Test the repository](../tutorials/advanced/testing.md).

## Jobs

Three workflows check a pull request. [validate.yaml](../../.github/workflows/validate.yaml) calls the shared
`gitops-validate` workflow, which reports its jobs as `validate / validate / <job>`:

- `changes` decides whether the pull request needs the full run. One that changes nothing the tests read skips
  `validate`, `get-diff` and `test_on_kind`, and runs the tests in `tests/ats` that need no cluster on their own in
  `test_without_cluster` (see [The light run](#the-light-run)).
- `check-pre-commit` runs every `pre-commit` hook of [.pre-commit-config.yaml](../../.pre-commit-config.yaml) on
  every file. Among them are [check-kustomization-paths](#check-kustomization-paths);
  [check-directory-readmes](../../tools/README.md#check-directory-readmes), which fails when a directory under
  `bases/` or `management-clusters/` has no README and no parent README covers it; and
  [check-sops-encrypted](../../tools/README.md#check-sops-encrypted), which fails when a `*.enc.yaml` file isn't
  encrypted with SOPS.
- `validate` runs `tools/test-all-ff validate`. It builds every Flux `Kustomization` that applies this repository, as
  Flux applies it, with the Flux CLI of the management clusters' Flux, which `test-all-ff` downloads. It passes the
  output through `yamllint` and `kubeconform`, so it fails on YAML that isn't valid and on objects that don't match
  their schemas. It also renders the chart of every `HelmRelease` with its merged values (see
  [validate-helm-values](../../tools/README.md#validate-helm-values)), so values the chart's schema rejects fail the
  job. It attaches a validation report as a comment to your pull request.

  An object a `ResourceSet` renders that keeps a `<< ... >>` template, such as one named after an entry of its
  `spec.inputs`, can't be checked without Flux Operator: the report names it as left out, and only the kind test
  checks it. A variable that a `Kustomization`'s manifests use but its `spec.postBuild.substitute` doesn't set fails
  the job, where Flux would replace it with an empty string. `flux build` doesn't read `spec.postBuild.substituteFrom`,
  so a variable set only there fails the job too, although Flux sets it on the cluster.

  It reads each `Kustomization` as Flux applies it: from the build of the Flux `Kustomization` that applies it, such as
  an organisation's namespace `Kustomization` for a workload cluster's, or else from the build of the directories
  above its file that have a `kustomization.yaml`, such as the organisation's, which sets `organization` (see
  [fake-flux](../../tools/README.md#fake-flux)).
- `get-diff` runs `tools/test-all-ff template` on the pull request and on its base branch, and attaches the
  difference between the two as a comment, so you see what your change does to the objects Flux applies.
- `test_on_kind` installs Flux on a kind cluster, applies the repository and checks that every `Kustomization` and
  source gets `Ready`, that the `HelmRelease`s the test cluster can run get `Ready`, and that the objects in
  `tests/ats/assertions` exist (see [The kind test](#the-kind-test)). It runs the pytest suite in `tests/ats`, whose
  checks that need no cluster run first. The checks of the template's examples run where the examples are (see
  [Example checks in a fork](#example-checks-in-a-fork)).

  Its last test, `test_prune`, checks pruning on the `out-of-band-no-flux` cluster. It deletes what the other tests
  check, so it runs last, and fails if they didn't run before it.

  First it leaves the organisation's `ORG_NAME.yaml` out of the `GitRepository` with `spec.ignore`. It also drops an
  app, `apps/hello-world-from-template`, from what the cluster's apps `Kustomization` builds, with `$patch: delete`
  patches in that `Kustomization`'s `spec.patches`: `apps/kustomization.yaml` lists the app, and `spec.ignore` can't
  change that list. The app has to go. The organisation's `kustomization.yaml` takes the organisation's name from the
  `Organization`, so without `ORG_NAME.yaml` the management cluster's `Kustomization`, `mc-name-gitops`, has to report
  that its build failed and prune nothing: its inventory keeps the `Organization` and the organisation's namespace
  `Kustomization`, and they stay. The namespace `Kustomization` depends on `mc-name-gitops`, so it has to report
  `DependencyNotReady` and prune nothing either: its inventory keeps the cluster's `Kustomization`s, and they stay.
  Once `ORG_NAME.yaml` is back, all three have to get `Ready` again.

  Next it drops the organisation's namespace `Kustomization` from what `mc-name-gitops` builds, with a
  `$patch: delete` patch in the `spec.patches` of `mc-name-gitops`, as deleting or renaming `namespace.yaml` would.
  `mc-name-gitops` has to drop it from its inventory, but it has to stay, with the cluster's `Kustomization`s: its
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation keeps Flux from deleting it. Once the patch is gone,
  `mc-name-gitops` has to list it again.

  Last it deletes the cluster's two `Kustomization`s. Everything they applied has to go, and the cluster's
  `HelmRelease` and `OCIRepository` have to stay.

[yaml-diff.yaml](../../.github/workflows/yaml-diff.yaml) posts a diff of the YAML files the pull request changes, as
they are in Git, before any build, leaving out encrypted files and key order.
[validate-file-names.yaml](../../.github/workflows/validate-file-names.yaml) checks that the files the pull request adds
or renames have ASCII-only names.

## check-kustomization-paths

[tools/check-kustomization-paths](../../tools/check-kustomization-paths) runs as a `pre-commit` hook. For every Flux
`Kustomization` (`kustomize.toolkit.fluxcd.io/v1`, or the older `v1beta2`) that applies this repository, outside
`tools/testdata`, it checks that `spec.path` exists and builds. This repository's `GitRepository` is the `sourceRef` of
the management cluster's own `Kustomization`, the one whose path is the directory of its file, such as `MC_NAME.yaml`. A
`Kustomization` with another source reads another repository, so it's left out. The hook builds a path that has a
`kustomization.yaml`, `kustomization.yml` or `Kustomization` with `kustomize build`, or with `kubectl kustomize` if
`kustomize` isn't installed. It builds a path without one the way Flux does, from the YAML files and the directories
with a kustomization file below it, and such a path must not be empty. It fails when it finds no `Kustomization`, no
management cluster `Kustomization` or when `yq` can't read them, rather than pass without checking anything. Otherwise
it fails, naming the `Kustomization`, its file and its path, when:

- the path doesn't exist: restore the directory, or delete the `Kustomization`, its file and its entry in the
  `kustomization.yaml` that lists it;
- the path is empty: delete the `Kustomization` the same way;
- a `kustomization.yaml` lists something that's gone, for example the directory of an app you removed from a
  cluster's `apps/`: remove the entry, or restore what it names.

On a cluster, each of these stops Flux applying the `Kustomization` until it's fixed, and it doesn't delete what the
`Kustomization` applied before. `tools/test-all-ff validate` checks that the hook fails on the fixture in
`tools/testdata/gone-path`, leaving out its `Kustomization` with another source, and on a directory without any
`Kustomization`.

## The kind test

The `test_on_kind` job checks more than the files: it applies them to a cluster, standing in for a new Giant Swarm
management cluster, and Flux reconciles them from your branch.

The test has two parts:

- The generic part works on whatever is under `management-clusters/`, in the template or in your fork. It applies the
  root `Kustomization` of each management cluster, stands in for the platform, waits for every `Kustomization`, source
  and `HelmRelease` to get `Ready` and enforces the platform's [admission policies](#admission-policies). It names
  nothing of the template's: it finds what it needs in the repository (see
  [What the test finds in the repository](#what-the-test-finds-in-the-repository)).
- The example part checks the template's examples beyond getting `Ready`: pruning, the upgrade windows, the out-of-band
  clusters, the secret stores and so on. [tests/ats/kind-test.yaml](../../tests/ats/kind-test.yaml) binds each check to
  the example it checks, and a check whose example isn't in the repository is skipped, saying why (see
  [Example checks in a fork](#example-checks-in-a-fork)).

Every example is something you build from, so an example the test can reconcile has to get `Ready`. The test installs
what an example needs; it doesn't skip examples to pass. Creating clusters is the one exception, as the test can't
do it (see [Cluster API](#cluster-api)).

### What the test finds in the repository

- **The management clusters.** Every directory `management-clusters/<name>` with a `<name>/<name>.yaml` is a management
  cluster, and that file holds its root `Kustomization`, the one whose `spec.path` is the directory. `managementClusters`
  in `kind-test.yaml` narrows the list (see [Configure the kind test](#configure-the-kind-test)).
- **The `GitRepository`s.** The test creates the `GitRepository` each root names in `spec.sourceRef`, in its namespace,
  pointed at the branch of the pull request. When `GITHUB_TOKEN` is set, as the shared workflow sets it to the run's
  token, the `GitRepository` reads the repository with it, so a private repository works. The root's own `ignore` and
  credentials, which you applied by hand on the management cluster, aren't in the repository, so the test's
  `GitRepository` has neither. Mind which commit that is: the shared workflow runs the test code of the pull request
  merged with its base branch, but Flux in the kind cluster reads the head of the pull request's branch,
  `GITOPS_REPO_BRANCH`. A branch behind its base can fail for something that isn't its own, such as a fixture the base
  removed that the branch's manifests still need. Update the branch from its base before you read a failure as yours.
- **The master key.** The test creates the Secret each root names in `spec.decryption.secretRef`, holding the key in
  `GITOPS_MASTER_GPG_KEY`, as you apply it by hand on a new management cluster. Flux then applies the encrypted copy
  in the repository over it. The key is needed only when a root decrypts: a repository that uses External Secrets
  Operator only needs no key at all.
- **The organisations.** Once the roots are `Ready`, the
  [organization-operator stand-in](#the-organization-operator-stand-in) creates the namespace of every
  `Organization` in the cluster.
- **The clusters.** Every Cluster API `Cluster` a `Kustomization` health-checks gets a stand-in (see
  [Cluster API](#cluster-api)).

All the root `Kustomization`s go into the one kind cluster, so the roots of several management clusters have to be
able to share it, and `GITOPS_MASTER_GPG_KEY` has to hold the key of every root that decrypts, exported together into
one armoured block.

### Configure the kind test

[tests/ats/kind-test.yaml](../../tests/ats/kind-test.yaml) holds what the test can't find in the repository. Every key
is optional, and the test fails on one it doesn't know, rather than ignore a typo:

| Key | What it is |
| --- | --- |
| `managementClusters` | The directories under `management-clusters/` whose root the test applies. Without it, every management cluster. |
| `examples` | The example checks, by example: `paths`, the files and directories of the repository the checks need, and `assertions`, the files and directories under `tests/ats/assertions` that assert the example's objects. |
| `nodePools` | The node pools of each workload cluster's `HelmRelease`, by namespace, then by cluster. See [Node pools](#node-pools). |
| `clusterBaseApps` | The `HelmRelease`s a cluster's `Kustomization` applies before its `Cluster` is `Available`, by the `Cluster`'s `namespace/name`. See [Cluster API](#cluster-api). |
| `secretStore` | The stand-in for your secret manager: a `SecretStore` with the [fake provider](https://external-secrets.io/latest/provider/fake/), its `name` and its `data`, the keys and values it serves. The test creates it in `default` and in every organisation's namespace. Without it, there's no stand-in. |

The stand-in store only stands in where nothing else has the name: a `SecretStore` of the same name in the repository
replaces it when Flux applies the namespace. So it serves `ExternalSecret`s that read a store the repository doesn't
create, as the template's examples do.

### Example checks in a fork

Each example check names its example in `kind-test.yaml`. When a path of the binding isn't in the repository, or is
in a management cluster the test doesn't apply, the check is skipped, and pytest's summary gives the reason, such as:

```text
SKIPPED [1] The example 'prune' isn't in this repository: management-clusters/MC_NAME/organizations/ORG_NAME/ORG_NAME.yaml
isn't in the repository. Its binding is in tests/ats/kind-test.yaml.
```

Setting up for an example works the same way: without its binding's paths, the test creates no vCluster for
`out-of-band-no-flux`, suspends no notification example `Alert` and forces no `ResourceSetInputProvider`. The assertion
files an example's binding names are left out with it, and every other assertion file is checked.

In the template's own CI, where `GITHUB_REPOSITORY` is `giantswarm/gitops-template`, an example that can't be found
fails the run instead: there, it's a binding that's gone wrong. That covers the example checks, the assertion files of
every example, and `test_the_template_binds_every_example_it_has`, which also checks, without a cluster, that every
assertion file in the template belongs to an example. The template is recognised by that repository name and nothing
else, so a copy under another name, a renamed template included, skips where the template would fail.

The checks that need no cluster work the same way: the ones of the repository's structure, in `test_root_build.py` and
`test_namespace_build.py`, run on the root of every management cluster the test applies; the ones that pin the
examples' files are bound to the examples.

### What the test proves, and what it can't

It proves that Flux, at the version of the management clusters, can apply every file your management clusters' roots
reach, that each `Kustomization` and source gets `Ready`, that the `automation` ServiceAccounts' rights and the admission
policies of a management cluster let them, that your SOPS files decrypt with your master key, and that the apps whose
cluster the test can reach install and get `Ready`.

It stands in for three things it can't have:

- **Cluster creation.** A `release-aws` `HelmRelease` is checked, not run: there's no cloud account. Its `Cluster` is a
  paused stand-in that the test sets `Available`, and the apps of a cluster the test has no kubeconfig for aren't
  installed. The template's `out-of-band-no-flux` example gets a vCluster; your clusters don't.
- **Your secret manager.** The kind cluster can't reach AWS Secrets Manager or Azure Key Vault, and has no workload
  identity. An `ExternalSecret` that reads a real store doesn't sync, and a `HelmRelease` that needs the Secret it would
  write doesn't get `Ready`: give that store's name and test values to `secretStore` when the repository doesn't
  create the store, or list the `HelmRelease` in `GITOPS_IGNORED_OBJECTS`.
- **The rest of the platform.** organization-operator, rbac-operator and the Kyverno policy that copies
  `cluster-app-installation-values` are stood in for; app-operator, cluster-apps-operator and the monitoring stack
  don't run.

Your own `Alert`s aren't suspended: an `Alert` that posts commit statuses to GitHub with a token from your repository
posts them for the kind test's `Kustomization`s too.

### What it checks

The objects named in `GITOPS_IGNORED_OBJECTS` that are `HelmRelease`s or sources aren't looked at at all. The list
doesn't apply to `Kustomization`s. The test checks:

| Objects | Check |
| --- | --- |
| `Kustomization`s | All of them get `Ready`, including the ones `GITOPS_IGNORED_OBJECTS` names. The test lists them again after each wait, as the root `Kustomization`s create the cluster ones, until no new one appears. Without any `Kustomization`, the test fails. |
| Sources: `OCIRepository`s, `GitRepository`s, `HelmRepository`s, `HelmChart`s and `Bucket`s | All of them get `Ready`. An OCI `HelmRepository` has no `Ready` condition, as Flux doesn't reconcile it, so it only has to exist. If there are none of a kind, the test passes and logs it. |
| `HelmRelease`s | Their references exist, and the ones the test cluster can run get `Ready` (see below). If there are none, the test passes and logs it. |

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

The test also loads every file in `tests/ats/assertions/exists` and checks it against the cluster, except the files of
an example that isn't there (see [Example checks in a fork](#example-checks-in-a-fork)). Each file holds one or more
Kubernetes objects, in YAML, that you expect in the cluster once Flux has applied your `Kustomization`s. Each object
needs `kind:`, `metadata.name` and, if it's namespaced, `metadata.namespace`. The rest is up to you, but every field the
file sets has to be on the object in the cluster, with exactly the same value. Strings are compared as text, so a
ConfigMap's `values` has to match line by line. Only trailing whitespace is ignored: whether the assertion writes a
block as `|` or `|-`, or a line ends in a space, doesn't matter.

### Node pools

A cluster's node pools come from several ConfigMaps in the `valuesFrom` of its `HelmRelease`, so no single assertion
shows them. For every `HelmRelease` that creates a workload cluster, the test reads the `HelmRelease` and its
ConfigMaps from the test cluster, merges the values the way helm-controller does, `spec.values` included, and compares
the node pools with `nodePools` in [kind-test.yaml](../../tests/ats/kind-test.yaml), by the cluster's namespace and
name. In the template, a production cluster gets its own `nodepool0` and its region's extra pool; dev and staging have
no pools of their own and get the chart's defaults. The `scheduled-upgrades` cluster gets `workers` from its own
values, which a patch on its `ResourceSet` appends, so the test also shows that the patch reaches the `HelmRelease` the
`ResourceSet` renders. In a namespace `nodePools` lists, the test fails for a workload cluster that isn't listed, so
when you add a cluster there or change its node pools, update the list. A namespace it doesn't list isn't checked,
and nor is a listed one without any cluster, such as `org-org-name` in a fork without the examples. Without
`nodePools`, `test_node_pools` is skipped.

## Versions

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
and `CiliumNetworkPolicy`. It also lowers the CPU requests of the image automation, image reflector and notification
controllers, which the test gives little to do, to 10m, so that the vCluster's apps fit on the kind node. The shared
workflow still installs `apptestctl`, at its own default version, but nothing uses it.

The shared workflow doesn't take a node image, so the Kubernetes patch version is whatever the kind release defaults
to. pytest prints the version it ran against at the top of its output, as `kubernetes server: v1.36.1 (linux/amd64)`.

## Cluster API

This repository doesn't test cluster creation. Workload clusters are created by the `release-aws` chart on a real
management cluster, which a kind cluster can't stand in for.

The test cluster has the Cluster API core CRDs only: the `CustomResourceDefinition`s from the `core-components.yaml`
of the Cluster API release, in the `cluster.x-k8s.io` group and its `addons`, `ipam` and `runtime` subgroups. It runs no
Cluster API controllers and no infrastructure providers such as CAPA or CAPZ, so nothing acts on a Cluster API object.
A test can create one, for example a stand-in `Cluster`, and set its status itself. Use `v1beta2`, the version the
objects are stored in: the CRDs are installed without their conversion webhook, so other versions are served without
conversion.

The test does that for every `Cluster` a `Kustomization` health-checks, as the cluster `Kustomization` of the basic
tutorial and the examples does: [cluster_gates.py](../../tests/ats/cluster_gates.py) finds them in the test cluster once
the organisations' `Kustomization`s have applied them, with the `Kustomization`s that depend on each: its apps. It
creates a paused stand-in `Cluster` with a node pool short of its minimum, so `WorkersAvailable` and `Available` stay
`False` throughout. At first its `ControlPlaneAvailable` and `RemoteConnectionProbe` are `False` too. The cluster's
`Kustomization` still has to apply the base apps that `clusterBaseApps` in `kind-test.yaml` names for it, while the
apps `Kustomization`s have to report `DependencyNotReady` without applying anything. Then it sets both to `True`, and
the apps `Kustomization`s have to get `Ready`, though the cluster still isn't `Available`. `test_apps_wait_for_cluster`
reports the result. The other checks run after it, as the cluster `Kustomization`s only get `Ready` once their
`Cluster`'s control plane is up.

A cluster you add gets its stand-in without anything to list; list its base apps if it has any. For its stand-in to
open the gate, its health check has to wait for the control plane, as the tutorial's does: one that waits for
`Available` never gets `Ready` in the test. For the example organisation, a test without the cluster checks that each
cluster `Kustomization`'s health check waits for the control plane and not for `Available`.

The shared workflow still installs `clusterctl`, at its own default version, but nothing uses it.

## The organization-operator stand-in

The test bootstraps the repository as a new management cluster does: no `Organization` and no `org-*` namespace exist
before Flux applies the roots. On a management cluster, organization-operator creates an organisation's namespace once
Flux has applied the `Organization`, and other operators fill it. The kind cluster runs none of them, so
[tests/ats/organization_operator.py](../../tests/ats/organization_operator.py) stands in for them, for every
`Organization` the roots apply, whatever its name. In the template, that's `org-name`, applied by `mc-name-gitops`:

1. Before Flux applies the roots, it checks that no `Organization` and no `org-*` namespace exists.
1. It waits for every root to get `Ready`, which applies the `Organization`s. For each one, it waits for the
   `Kustomization`s that apply into its namespace from another one, such as the organisation's namespace
   `Kustomization`, `mc-name-organization-org-name`, to fail for want of it. Its `dependsOn` holds it back until the
   root is `Ready`, and then its error names the namespace, `org-org-name`: the namespace doesn't exist, or
   `default/automation` may not write there, as it gets its rights in the namespace only with it.
1. It creates the namespace, and in it what the management cluster's operators create there: `automation` and the
   rights rbac-operator gives in a new organisation namespace (see
   [The rights of the `automation` ServiceAccounts](#the-rights-of-the-automation-serviceaccounts)); the
   `cluster-app-installation-values` ConfigMap, which Kyverno copies there; and the stand-in secret store, if
   `kind-test.yaml` has one. In `org-org-name`, when the examples are there, it also creates the notification example's
   commit-status `Alert`, suspended, before Flux can apply it, and the kubeconfig Secret and cluster values of the
   [vCluster](#the-out-of-band-no-flux-workload-cluster).
1. Without asking Flux to reconcile, it waits up to 150 seconds, two `retryInterval`s and a margin, for those
   `Kustomization`s to get `Ready` on their own retry.

The other checks run after it. The cluster `Kustomization`s are in the organisation's `workload-clusters` directory,
which its `namespace/kustomization.yaml` lists, so they appear only once the organisation's `Kustomization` is `Ready`,
and run as the organisation's `automation`. `test_automation_access` checks the rights of `automation` in every
organisation's namespace. `tests/ats/test_root_build.py` checks, without a cluster, that the build of each root holds
only `Organization`s and objects in `default`, that each organisation's namespace `Kustomization` applies into the
organisation's namespace, that every `Kustomization` in it other than the root depends on the root, and that every
`Kustomization` in it, the root included, has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation (see
[Deletion protection](../explanation/deletion-protection.md#the-protected-objects)).
`tests/ats/test_namespace_build.py` checks that the `Kustomization`s it applies read the repository's `GitRepository`
in `default`, depend on it, directly or through another of them, and decrypt with a key Secret it applies too.

## The rights of the `automation` ServiceAccounts

A `Kustomization` or `HelmRelease` with `serviceAccountName: automation` runs as the `automation` ServiceAccount of its
namespace, which [rbac-operator](https://github.com/giantswarm/rbac-operator) creates in `default` and in every `org-*`
namespace of a management cluster. The test gives these ServiceAccounts exactly the rights they have there, so an
example that a management cluster would refuse with `Forbidden` fails the test too. The `automation_rbac` fixture in
[tests/ats/automation_rbac.py](../../tests/ats/automation_rbac.py) creates them for `default` once every CRD of the test
is installed, and [the organization-operator stand-in](#the-organization-operator-stand-in) for the organisation's
namespace once it exists, as rbac-operator does for a new organisation namespace. It replaces an existing one whose
rules or subjects differ, as rbac-operator does. The API server doesn't let it change a binding's role, so it deletes
and creates again a binding whose role differs, as `kubectl auth reconcile` does. `test_automation_access` in
[tests/ats/test_flux_objects.py](../../tests/ats/test_flux_objects.py) then asks the cluster with `SubjectAccessReview`s
whether each ServiceAccount may and may not do the things that
[tests/ats/automation_access.py](../../tests/ats/automation_access.py) lists, so it also fails when something else, such
as an object left over from an earlier run, grants more. Everything else the test sets up, such as Flux, Kyverno,
External Secrets Operator, the vCluster, the stand-in clusters and the fixtures, uses the test's admin client.

`default/automation`:

- `cluster-admin` in `default`, through a `RoleBinding`, and in every `org-*` namespace except `org-giantswarm`;
- `read-all` in every namespace: `get`, `list` and `watch` on every resource the API server serves, except
  `ConfigMap`s and `Secret`s, and `get` and `list` on `pods/log`;
- all verbs on `Organization`s and, on CAPA management clusters, `AWSClusterRoleIdentity`s, which are
  cluster-scoped;
- in every namespace: all verbs on `CertConfig`s, `Silence`s and Kyverno `PolicyException`s.

`org-<organisation>/automation`:

- `cluster-admin` in its own namespace only;
- in every namespace: all verbs on `Silence`s;
- `get`, `list` and `watch` on the cluster-scoped `Release`s, `Node`s and `AWSClusterRoleIdentity`s, which the
  cluster charts look up;
- all verbs on `PolicyException`s in `kube-system`, `giantswarm` and `policy-exceptions`, and `get`, `list` and `patch`
  on `Chart`s in `giantswarm`;
- the role of the Kamaji app, where it runs, which the kind cluster doesn't.

Neither can create namespaces, cluster-scoped objects other than `Organization`s and `AWSClusterRoleIdentity`s, or
RBAC outside the namespaces where it's `cluster-admin`. `org-<organisation>/automation` can't read other namespaces
beyond those.

Kyverno's background controller, `kyverno/kyverno-background-controller`, gets the `ClusterRole`
`write-kyverno-generated-externalsecrets` in every `org-*` namespace, through a `RoleBinding`: all verbs but
`deletecollection` on `ExternalSecret`s and `SecretStore`s, and `get`, `list` and `watch` on `Secret`s. It lets a
Kyverno policy in an organisation's namespace generate them, such as the
[workload cluster secret store example](../how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno).
[tests/ats/kyverno_rbac.py](../../tests/ats/kyverno_rbac.py) holds the role and its bindings, and
`test_automation_access` checks, with [tests/ats/kyverno_access.py](../../tests/ats/kyverno_access.py), that it may
create `ExternalSecret`s in the organisation's namespace and not in `default`.

The rules are copied from rbac-operator at commit `4681152f3de2a062788baa7ecd44a2882acbce5d`, Kyverno's from the
not yet released `80aed29e11e49eac3a7f77b601c6df124e66cfe4`, and the `RoleBinding`s of Giant Swarm's Flux from
management-cluster-bases at `52aa8ee8a4ddb0c95e693bac67556150e33d956f` and flux-app at
`02f4e84fa7a585de8e0deb95983ea47a4cbf828c`. [tests/ats/automation_roles.py](../../tests/ats/automation_roles.py) holds the
rules, [tests/ats/automation_bindings.py](../../tests/ats/automation_bindings.py) and
[tests/ats/automation_accounts.py](../../tests/ats/automation_accounts.py) the bindings, and each names the file and
lines each object comes from. rbac-operator builds `read-all` from the API server's discovery, so the test
does too: it covers the resources served when the fixture runs. The test leaves out the binding to Crossplane's
`crossplane-edit`, which rbac-operator creates only where Crossplane runs. When rbac-operator changes the rights, update
the modules and the commits.

## Admission policies

Rights decide what `automation` may do; two Kyverno `ClusterPolicy`s decide which Flux objects a management cluster
admits at all. Every Giant Swarm management cluster enforces them, and so does the kind test, from
[tests/ats/fixtures/admission-policies](../../tests/ats/fixtures/admission-policies/README.md), copied from
management-cluster-bases at `54ec7bdb049a14d343999107abe7174cb65fd9f2`. The `admission_policies` fixture applies them
once Kyverno runs and waits until both are `Ready`, before Flux applies the repository. An object that breaks a rule is
refused, its `Kustomization` fails, and so does the test.

Outside `flux-giantswarm`, `giantswarm` and `monitoring`:

- `flux-multi-tenancy`: a `Kustomization` or `HelmRelease` sets `serviceAccountName`, or a kubeconfig with
  `spec.kubeConfig.secretRef`. Its `targetNamespace` is its own namespace or an `org-*` namespace other than
  `org-giantswarm`, unless it has a kubeconfig. A `HelmRelease`'s `storageNamespace` is its own namespace, unless it
  has a kubeconfig. A `Kustomization`'s `sourceRef` and a `HelmRelease`'s chart source are in its own namespace or
  `default`. An `Alert`'s event sources, a `Receiver`'s resources and an `ImagePolicy`'s `ImageRepository` are in its
  own namespace.
- `flux-operator-multi-tenancy`: a `ResourceSet` sets `serviceAccountName`, and a `FluxInstance` exists only in
  `flux-giantswarm`.

When management-cluster-bases changes them, copy them again and update the commit in the files, in their README and in
`SOURCE_COMMIT` in [tests/ats/admission_policies.py](../../tests/ats/admission_policies.py).

## The `out-of-band-no-flux` workload cluster

This part of the test belongs to the example: its binding in `kind-test.yaml` is `out-of-band-no-flux`, and without the
example there's no vCluster, and the tests that use it are skipped.

`WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload cluster, and the cluster's
`HelmRelease`s install their apps there, through the `out-of-band-no-flux-kubeconfig` Secret a management cluster has
for it. The test installs a [vCluster](https://www.vcluster.com/) named `out-of-band-no-flux` in the test cluster, and
[the organization-operator stand-in](#the-organization-operator-stand-in) puts its kubeconfig, with the vCluster's
in-cluster Service as the server, in that Secret once the organisation's namespace exists, so the `Kustomization` and
the `HelmRelease`s reconcile as they would on a management cluster. As that Secret exists, the apps have to get `Ready`.
The test also creates what they need:

- the `out-of-band-no-flux-cluster-values` ConfigMap, which a management cluster creates for every workload
  cluster. Its values are [tools/values-stubs/cluster-values.yaml](../../tools/values-stubs/cluster-values.yaml).
- in the vCluster, the CRDs that a Giant Swarm workload cluster gets from its default apps and the apps create objects
  of: Cilium's `CiliumNetworkPolicy`, `PodMonitor`, Grafana's `PodLogs`, cert-manager's `Certificate` and `Issuer`,
  Kyverno's `ClusterPolicy` and external-dns' `DNSEndpoint`. Only the CRDs: nothing in the test needs their
  controllers. They're kept in [tests/ats/fixtures/crds](../../tests/ats/fixtures/crds/README.md), which says where
  each comes from, so the test doesn't download them.
- in the vCluster, the `giantswarm-critical` PriorityClass, which the cluster chart creates in every Giant Swarm
  workload cluster. The `envoy-gateway` Deployment's pods can't be created without it.

The vCluster runs CoreDNS, as the apps run pods there.

Every file in `tests/ats/assertions/exists-in-workload-cluster` is verified against the vCluster, the same way as the
files in `tests/ats/assertions/exists`. They list the main workload of each app:

- Every workload-cluster app whose kubeconfig Secret exists needs an assertion of its main workload: an object with a
  `helmRelease: <namespace>/<name>` key naming the `HelmRelease`. The key isn't a field of the object, so the
  comparison skips it. The test fails for a `HelmRelease` without one, so a new app needs an assertion. For
  `gateway-api-crds`, which runs no workload, it's the `gateways.gateway.networking.k8s.io` CRD the chart installs.
- Every `Deployment` in them has to be available, too. That includes the `podinfo` `Deployment` that the
  [application team](../tutorials/advanced/teams.md) `hello-team` delivers from its own repository into its namespace.
  Its `Kustomization` runs as the `automation` ServiceAccount of `org-org-name`, which the organization-operator
  stand-in creates with the rights a Giant Swarm management cluster gives it.
- The `giantswarm-default` `Gateway` of the `gateway-api-config` app only has to exist. kind has no load balancer for
  its Service, so the `Gateway` can't be `Programmed`. Its `HelmRelease` gets `Ready` all the same.

The kind cluster is one node on a CI runner, so the vCluster's pods take their CPU requests from the same 4 CPUs as
everything else. After the `HelmRelease`s are `Ready`, `test_kind_node_has_room` checks that the node can still take
what the apps will add: each `HorizontalPodAutoscaler` scaling its `Deployment` up to `minReplicas`, and the largest
rollout surge, as `test_values_change_applied_at_once` rolls out one app. It counts the requests of every pod but a
`Job`'s, scheduled or not, and fails with the numbers unless 200m CPU stay free. Without that room one app's pods stay
`Pending` with "Insufficient cpu", and which app changes from run to run
([#368](https://github.com/giantswarm/gitops-template/issues/368)). So the fixtures lower the CPU requests of the
test's own infrastructure: the vCluster, Kyverno, Flux Operator, ESO, and the Flux controllers the test gives little to
do. Requests only decide where a pod fits; each can still use up to its limits. A new app in the vCluster that doesn't
fit fails this test: lower another fixture's requests, not the example's.

When a test that uses the vCluster fails, its report has a `workload cluster diagnostics` section: the `HelmRelease`s
that install into the vCluster, what the pods on the kind node request against what it can give, and in the vCluster
the Helm history, `Deployment`s, `ReplicaSet`s, `HorizontalPodAutoscaler`s, `PodDisruptionBudget`s, pods, events and
the logs of the pods that aren't ready.

To run the test on your machine, follow
[Run the kind test locally](../tutorials/advanced/testing.md#run-the-kind-test-locally): pytest has to reach the vCluster
on the kind node's network.

`tests/ats/conftest.py` pins the `vcluster` chart (`VCLUSTER_CHART_VERSION`, 0.37.6) and the vCluster's Kubernetes image
(`VCLUSTER_KUBERNETES_IMAGE_TAG`, v1.36.6). Keep the image on the Kubernetes minor version of the kind cluster and the
management clusters when you bump either. A vCluster runs as a pod in the kind cluster, so more workload clusters cost a
pod each rather than another kind cluster on the runner. In a
[comparison](https://github.com/giantswarm/gitops-template/pull/277) with a second kind cluster, the vCluster took 29
seconds to set up against 17 (medians of 6 and 15 runs), and the whole kind job 254 seconds against 237, less than the
spread of about 60 seconds between runs of the same setup.

## Kyverno

Kyverno runs on every Giant Swarm management cluster, and the External Secrets Operator chart creates its
`PolicyException`s only when Kyverno's CRDs are there, so the test installs Kyverno before ESO. It installs Giant
Swarm's charts, the ones team Shield ships to the management clusters, from `oci://gsoci.azurecr.io/charts/giantswarm`:
`kyverno-crds` 1.19.2, as the `kyverno` chart leaves the CRDs to it, then `kyverno` 0.26.2, the chart of `kyverno-app`.
Kyverno's pods use the `giantswarm-critical` PriorityClass and its `PolicyException`s go in the `giantswarm` namespace,
which every management cluster has, so the test first installs Giant Swarm's `priority-classes` 0.3.1 chart and creates
the namespace. The charts are pinned in `tests/ats/kyverno_install.py`.
[tests/ats/fixtures/kyverno-values.yaml](../../tests/ats/fixtures/kyverno-values.yaml) turns off the objects whose CRDs
the kind cluster doesn't have: the `CiliumNetworkPolicy`s, `PodLogs`, `VerticalPodAutoscaler`s and `ServiceMonitor`s. It
also lowers the controllers' CPU requests, and the background and reports controllers' memory from the chart's 1Gi,
which are sized for a management cluster, so that the vCluster's apps still fit on the single kind node.

## Flux Operator

The [upgrade window examples](../tutorials/advanced/scheduled-upgrades.md) are Flux Operator `ResourceSetInputProvider`s
and `ResourceSet`s, so the test installs Flux Operator before Flux applies the repository. It installs Giant Swarm's
`flux-operator` chart 0.9.0 (Flux Operator v0.62.1), the version management-cluster-bases deploys, from
`oci://gsoci.azurecr.io/charts/giantswarm`, into `flux-giantswarm`. The chart is pinned in
`tests/ats/flux_operator_install.py`.
[tests/ats/fixtures/flux-operator-values.yaml](../../tests/ats/fixtures/flux-operator-values.yaml) has the chart install
the CRDs, which a management cluster gets from management-cluster-bases, turns off the `VerticalPodAutoscaler` and the
`ServiceMonitor`, and lowers its CPU request to 10m.

A new provider whose window is closed exports no version, so once the `Kustomization`s are `Ready`, the test forces
each example's provider once and waits for its `ResourceSet`, before it checks the sources and `HelmRelease`s. Then:

- `test_schedule_window` checks what `schedule.window` does, on providers of its own.
- `test_scheduled_cluster_upgrade` moves the `scheduled-upgrades` cluster to an older release, then to its range with
  the window closed, where the release has to stay, then opens the window, where it has to move.
- `test_input_loss_keeps_the_app` takes the version of the hello-world example away, by an unreadable registry, a
  range no tag matches and a deleted provider, and checks that the `ResourceSet` waits and the app stays installed.
- `test_input_loss_keeps_the_cluster` does the same to the `scheduled-upgrades` cluster, and then deletes its
  `ResourceSet`. The cluster's `HelmRelease` and `OCIRepository` have to stay each time.
- `test_move_to_scheduled_upgrades` moves the running `capi-wc-name` cluster, the `WC_NAME` example, to the layout of
  the scheduled-upgrades example, as [Move a running cluster to scheduled
  upgrades](../how-to/scheduled-upgrades-existing-cluster.md) does, but without a commit. It suspends the cluster's
  `Kustomization`, applies the provider and the `ResourceSet` built from the moved directory, pinned to the release the
  cluster runs, and forces the provider. The `ResourceSet` has to take the `HelmRelease` and `OCIRepository` over with
  the same `valuesFrom`, and their specs mustn't change otherwise: the chart reference, the tag and the values are what
  helm-controller upgrades a release on. The kind test never installs a cluster chart, as `release-aws` can't render
  without a real management cluster, so the check can't watch for an upgrade itself: the evidence that unchanged specs
  mean no upgrade comes from helm-controller's source, not from the test. Then it deletes the provider and the
  `ResourceSet`, takes the `ResourceSet`'s labels off the objects and resumes the `Kustomization`. It doesn't push the
  move to Git, so it doesn't show that Flux lets go of the objects when their files go; `test_prune` shows that for the
  `prune: disabled` annotation.

The assertions in `tests/ats/assertions/exists/organizations/workload-clusters/scheduled-upgrades` check that the
cluster's `ResourceSet`, not its `Kustomization`, renders the cluster's `OCIRepository` and `HelmRelease`, with the
protection of the cluster base and the cluster's own values. `tests/ats/test_cluster_move.py` builds the move of
`WC_NAME` without a cluster, and fails if the `HelmRelease` the `ResourceSet` renders lacks a `valuesFrom` entry of the
cluster's own `HelmRelease`, or has them in another order. `tests/ats/test_delete_protection.py` builds the
scheduled-upgrades example with the patch that [Delete a workload cluster](../how-to/delete-cluster.md) writes for a
cluster a `ResourceSet` renders, and fails unless the rendered `OCIRepository` and `HelmRelease` have lost the
`giantswarm.io/prevent-deletion` label and the release's values set `preventDeletion` to `false`. The kind test
doesn't remove the deletion protection of either kind of cluster: `test_prune` deletes a cluster's `Kustomization`s and
checks that its `HelmRelease` and `OCIRepository` stay, but doesn't take the protection off or delete the cluster.

They change the providers with the `Kustomization` that applies them suspended, and resume it afterwards. The
hello-world example's `HelmRelease` for the `out-of-band-no-flux` cluster installs into the vCluster, so it's in
`tests/ats/assertions/exists-in-workload-cluster`; `test_prune` leaves it out of the apps it expects to go with the
cluster's `Kustomization`s, as an organisation's `ResourceSet` installs it.

## Example checks

Some examples get a test of their own, beyond getting `Ready`. Each is bound to its example in `kind-test.yaml`, and
skipped where the example isn't (see [Example checks in a fork](#example-checks-in-a-fork)).

### Shared objects

`test_shared_object_copied` checks the [shared-objects example](../how-to/share-objects.md). Every organisation whose
`namespace/shared-objects` lists the base has to have the `shared-ca-bundle` ConfigMap in its namespace, with the data
of the base in Git, so a change to the base reaches every copy. The test then changes one copy, asks Flux to reconcile
the organisation's namespace `Kustomization`, which applied it, and waits for Flux to put the copy back.
`tests/ats/test_shared_objects.py` checks, without a cluster, that the example organisation lists the base.

### Commit statuses

The kind test creates both commit-status `Alert`s suspended, so it posts nothing to GitHub, and
`tests/ats/assertions/exists/notifications` checks that Flux applied them as the repository has them.
`tests/ats/test_commit_status.py` checks, without a cluster, that each `Alert`'s `exclusionList` drops the event
kustomize-controller sends while a `Kustomization` waits for its `dependsOn`, and none of its other events (see
[Report reconcile status on GitHub commits](../how-to/commit-statuses.md#check-the-statuses)).

### Workload cluster secret stores

`test_workload_cluster_secret_store` checks the
[workload cluster secret store example](../how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno),
the organisation's Kyverno `Policy`, with the vCluster's kubeconfig Secret, which the test labels and types as Cluster
API does. Kyverno's background controller needs rights in the organisation's namespace that rbac-operator grants on a
management cluster and the example doesn't ship; the organization-operator stand-in creates them with the others
(see [The rights of the `automation` ServiceAccounts](#the-rights-of-the-automation-serviceaccounts)). Flux applies
the `Policy` as `default/automation`, and the `default` store reads the organisation's namespace as its `automation`.

The kubeconfig Secret is there before Flux applies the `Policy`, so the test goes through `generateExisting`. The test
waits for the organisation's `SecretStore` `default`, `out-of-band-no-flux-eso-cluster-auth` and the
`out-of-band-no-flux-eso-cluster-store` `SecretStore`, then reads a Secret from the vCluster through that store and
checks its value. It then waits for the
[`PushSecret` example](../how-to/workload-cluster-secrets.md#push-a-generated-password) to get `Ready` and for the
`pushed-password` Secret it writes into the vCluster's `default` namespace to have a `password` of the generator's 32
characters. On a management cluster, the ESO chart's `CiliumNetworkPolicy` lets ESO reach the cluster and the world.
The kind cluster has no Cilium, so the `NetworkPolicy` in `tests/ats/workload_cluster_secrets.py`, which the
[workload cluster secrets example](#workload-cluster-secrets) needs too, gives ESO the same egress.

The [kubeconfig example](../how-to/workload-cluster-secrets.md#push-a-clusters-kubeconfig-to-another-cluster)
pushes to `tools-cluster`, which the test hasn't got: the stand-in writes `tools-cluster-kubeconfig` with the
vCluster's kubeconfig too, so the vCluster stands in for both clusters. Its check,
`test_kubeconfig_pushed_to_another_cluster`, is bound as `pushed-kubeconfig` in `kind-test.yaml`, and without the
example the stand-in writes no `tools-cluster-kubeconfig`. The test waits for
`tools-cluster-eso-cluster-store` to get `Ready`, then for the `PushSecret` to get `Ready` and for the
`out-of-band-no-flux-kubeconfig` Secret in the vCluster's `default` namespace to hold the same `value` as the
kubeconfig Secret on the management cluster.

Last, the test writes a kubeconfig Secret for a new cluster, `new-cluster-kubeconfig`, with the vCluster's kubeconfig,
and waits for the policy to react to it with `new-cluster-eso-cluster-auth` and a `Ready`
`new-cluster-eso-cluster-store` in the organisation's namespace, then deletes the Secret.

### Workload cluster secrets

The kind test runs the [workload cluster secrets example](../how-to/workload-cluster-secrets.md#push-secrets-through-a-store-in-git)
for real: it creates the test store, and the vCluster stands in for the workload cluster. It checks that both Secrets
are on the management cluster and in the workload cluster. The kind cluster has no Cilium, so a `NetworkPolicy` in
`tests/ats/workload_cluster_secrets.py` gives ESO the egress the chart's `CiliumNetworkPolicy` gives it on a
management cluster; the [workload cluster secret store test](#workload-cluster-secret-stores) relies on it as well.
CI can't reach a cloud secret manager, so `tools/test-all-ff validate` only builds each base in `bases/secret_stores`
and checks it against the schemas of its kinds.

### Pulled out-of-band directories

A workload cluster's own Flux pulls the `out-of-band` directory of the
[`out-of-band-flux-app`](../tutorials/advanced/out-of-band.md#run-flux-in-the-workload-cluster) example, so no
`Kustomization` in the repository builds it, and the kind test, which runs no Flux in a workload cluster, doesn't
apply it. `tools/test-all-ff validate` checks the manifests of every such directory against the schemas of their
kinds. That includes the [application team](../tutorials/advanced/teams.md) `hello-team-wc`, whose Flux runs in the
workload cluster.

### Object names

A schema doesn't cover an object's name, and the API server refuses one that isn't a lowercase RFC 1123 subdomain.
`tests/ats/test_object_names.py` checks, without a cluster, the name of every object in the YAML files of `bases/`
and `management-clusters/`, and of every object a `ResourceSet` there renders, with the variables Flux substitutes
filled in.

## The light run

[tests/ats/ci_scope.py](../../tests/ats/ci_scope.py) decides, for the `changes` job of `validate.yaml`, whether a pull
request gets the full run or the light one. It reads GitHub's list of the pull request's files, and checkouts of its
merge base and its head. The light run happens only when every file is one of these:

| The file | Why it doesn't count |
| --- | --- |
| `*.md`, anywhere | `tools/test-all-ff validate` reads no Markdown, except in the self-tests of `check-directory-readmes`, which depend on four READMEs under `bases/` and `management-clusters/`. A README change that breaks them also fails `check-directory-readmes` itself, a `pre-commit` hook that the light run runs as well. The kind test's checks that need no cluster read some Markdown, and the light run runs them too. |
| `docs/` | Documentation. Only checks that need no cluster read it, such as `test_delete_protection.py`, which tries the patch `docs/how-to/delete-cluster.md` writes, and the light run runs them. |
| `renovate.json5` | Read by Renovate only. |
| `tests/chainsaw/` | Run by `chainsaw.yaml` against a management cluster. `tools/test-all-ff` leaves out `tests/`, and `tests/ats` doesn't read it. |
| `.github/workflows/`, except `validate.yaml` and `validate-light.yaml` | The other workflows; neither test reads them. |
| `.gitignore`, `CODEOWNERS`, `LICENSE` | Read by git and GitHub only. |
| A YAML file whose parsed content is the same in both versions | Comments, whitespace, quoting and key order are all that changed. Document order, list order, tags and each value's type count; a duplicate key counts, as `kubeconform -strict` rejects it. |

A `*.yaml` file in the table that names a Flux API in either version counts even so: `tools/test-all-ff` reads every
`*.yaml` outside `tests/` and `tools/testdata/` that matches `api.*\.fluxcd\.io`, looking for the `Kustomization`s it
builds. A file added, removed or renamed counts unless both its paths are in the table. YAML that doesn't parse
counts. A list of files shorter than GitHub's count, an error, or a `changes` job that fails before it decides, means
the full run, as does every push to `main`.

The light run is [validate-light.yaml](../../.github/workflows/validate-light.yaml): `check-pre-commit` runs every
`pre-commit` hook, and `validate` and `test_on_kind` report as skipped, so the required checks have the same names
either way. One more job, `test_without_cluster`, runs every test in `tests/ats` that needs no cluster: all of them but
`test_flux_objects.py`. Those are the checks the kind test runs first, and some of them read a file as text, comment
and all. `test_org_name_references.py` finds the list of files in the organisation's `kustomization.yaml` by the
comment's first words, and `test_delete_protection.py` reads a heredoc out of `docs/how-to/delete-cluster.md`. Reword
one of those and the light run fails, as it should. The job installs Python and the packages `tests/ats/Pipfile.lock`
pins, as `test_on_kind` does, and `kubectl` for `kubectl kustomize`. It needs no secret, so it runs on a pull request
from a fork too. The shared workflow has no input to run `validate` without the kind test, so the two always run
together.
