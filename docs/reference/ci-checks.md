# CI checks

This page says what each CI job and test checks, and why. To set the workflows up in a fork, see
[Configure CI](../how-to/configure-ci.md). To run the same checks before you push, see
[Check a change before you push](../how-to/check-changes.md). To run the kind test on your machine or to test a
management cluster with Chainsaw, see [Test the repository](../tutorials/advanced/testing.md).

## Jobs

Three workflows check a pull request. [validate.yaml](../../.github/workflows/validate.yaml) calls the shared
`gitops-validate` workflow, which reports its jobs as `validate / validate / <job>`:

- `changes` lists the files the pull request changes. A pull request that changes only Markdown skips `validate`,
  `get-diff` and `test_on_kind`, see [When the workflows run](../how-to/configure-ci.md#when-the-workflows-run).
- `check-pre-commit` runs every `pre-commit` hook of [.pre-commit-config.yaml](../../.pre-commit-config.yaml),
  including [check-kustomization-paths](#check-kustomization-paths), on every file, and
  [check-directory-readmes](../../tools/README.md#check-directory-readmes), which fails when a directory under
  `bases/` or `management-clusters/` has no README, unless a parent README covers it.
- `validate` runs `tools/test-all-ff validate`. It builds every Flux `Kustomization` that applies this repository, as
  Flux applies it, and passes the output through `yamllint` and `kubeconform`, so it fails on YAML that isn't valid
  and on objects that don't match their schemas. It also renders the chart of every `HelmRelease` with its merged
  values (see [validate-helm-values](../../tools/README.md#validate-helm-values)), so values the chart's schema
  rejects fail the job. A variable that a `Kustomization`'s manifests use but its `spec.postBuild.substitute` doesn't
  set fails the job, where Flux would replace it with an empty string. `flux build` doesn't read
  `spec.postBuild.substituteFrom`, so a variable set only there fails the job too, although Flux sets it on the
  cluster. It reads each `Kustomization` as Flux applies it: from the build of the Flux `Kustomization` that applies
  it, such as an organisation's namespace `Kustomization` for a workload cluster's, or else from the build of the
  directories above its file that have a `kustomization.yaml`, such as the organisation's, which sets
  `organization`, see [fake-flux](../../tools/README.md#fake-flux). It attaches a validation report as a comment to
  your pull request.
- `get-diff` runs `tools/test-all-ff template` on the pull request and on its base branch, and attaches the
  difference between the two as a comment, so you see what your change does to the objects Flux applies.
- `test_on_kind` installs Flux on a kind cluster, applies the repository and checks that every `Kustomization` and
  source gets `Ready`, that the `HelmRelease`s the test cluster can run get `Ready`, and that the objects in
  `tests/ats/assertions` exist, see [The kind test](#the-kind-test). It runs the pytest suite in `tests/ats`.
  Its last test, `test_prune`, checks pruning on the `out-of-band-no-flux` cluster. It leaves the organisation's
  `ORG_NAME.yaml` out of the `GitRepository` with `spec.ignore`, and drops an app, `apps/hello-world-from-template`,
  from what the cluster's apps `Kustomization` builds with `$patch: delete` patches in its `spec.patches`, as
  `apps/kustomization.yaml` lists the app and `spec.ignore` can't change that list. The app has to go. The
  organisation's `kustomization.yaml` takes the organisation's name from the `Organization`, so without `ORG_NAME.yaml`
  the management cluster's `Kustomization`, `mc-name-gitops`, has to report that its build failed and prune nothing: its
  inventory keeps the `Organization` and the organisation's namespace `Kustomization`, and they stay. That one, which
  depends on `mc-name-gitops`, has to report `DependencyNotReady` and prune nothing either: its inventory keeps the
  cluster's `Kustomization`s, and they stay. Once `ORG_NAME.yaml` is back, all three have to get `Ready` again. Then it
  deletes the cluster's two `Kustomization`s. Everything they applied has to go, and the cluster's `HelmRelease` and
  `OCIRepository` have to stay. It deletes what the other tests check, so it runs last and fails if they didn't run
  before it.

[yaml-diff.yaml](../../.github/workflows/yaml-diff.yaml) posts a diff of the YAML files the pull request changes, as
they are in Git, before any build, leaving out encrypted files and key order.
[validate-file-names.yaml](../../.github/workflows/validate-file-names.yaml) checks that the files the pull request adds
or renames have ASCII-only names.

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
- a `kustomization.yaml` lists something that's gone, for example the directory of an app you removed from a
  cluster's `apps/`: remove the entry, or restore what it names.

On a cluster, each of these stops Flux applying the `Kustomization` until it's fixed, and it doesn't delete what the
`Kustomization` applied before. `tools/test-all-ff validate` checks that the hook fails on the fixture in
`tools/testdata/gone-path`, leaving out its `Kustomization` with another source, and on a directory without any
`Kustomization`.

## The kind test

The `test on kind` job checks more than the files: it applies them to a cluster.

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
its own `nodepool0` and its region's extra pool. Dev and staging have no pools of their own and get the chart's
defaults. The test fails for a workload cluster that isn't in `EXPECTED_NODE_POOLS`, so when you add a cluster or
change its node pools, update that table.

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
and `CiliumNetworkPolicy`. The shared workflow still installs `apptestctl`, at its own default version, but nothing
uses it.

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

The test does that for every cluster whose apps wait for it, as listed in `GATES` in
[cluster_gates.py](../../tests/ats/cluster_gates.py). It creates a paused stand-in `Cluster` with `Available` `False`.
The cluster's `Kustomization` still has to apply the base apps, while the apps `Kustomization` has to report
`DependencyNotReady` without applying anything. Then it sets `Available` to `True`, and the apps `Kustomization` has to
get `Ready`. `test_apps_wait_for_cluster` reports the result. The other checks run after it, as the cluster
`Kustomization`s only get `Ready` once their `Cluster` is `Available`. When you add a cluster with apps, add it to
`GATES`: a test without the cluster compares the list with the `Kustomization`s in the repository.

The shared workflow still installs `clusterctl`, at its own default version, but nothing uses it.

## The organization-operator stand-in

The test bootstraps the repository as a new management cluster does: no `Organization` and no `org-*` namespace exist
before Flux applies `MC_NAME.yaml`. On a management cluster, organization-operator creates the organisation's
namespace once Flux has applied the `Organization`, and other operators fill it. The kind cluster runs none of them,
so [tests/ats/organization_operator.py](../../tests/ats/organization_operator.py) stands in for them:

1. Before Flux applies `MC_NAME.yaml`, it checks that neither the `Organization` `org-name` nor the namespace
   `org-org-name` exists.
1. It waits for `mc-name-gitops` to get `Ready` and apply the `Organization`, which carries the
   `kustomize.toolkit.fluxcd.io/name: mc-name-gitops` label, and for the organisation's namespace `Kustomization`,
   `mc-name-organization-org-name`, to fail for want of the namespace. Its `dependsOn` holds it back until
   `mc-name-gitops` is `Ready`, and then its error names `org-org-name`: the namespace doesn't exist, or
   `default/automation` may not write there, as it gets its rights in the namespace only with it.
1. It creates `org-org-name`, and in it what the management cluster's operators create there: the organisation's
   commit-status `Alert`, suspended, before Flux can apply it; `automation` and the rights rbac-operator gives in a
   new organisation namespace, see [The rights of the `automation` ServiceAccounts](#the-rights-of-the-automation-serviceaccounts);
   the `cluster-app-installation-values` ConfigMap, which Kyverno copies there; the test's secret store; and the
   kubeconfig Secret and cluster values of the [vCluster](#the-out-of-band-no-flux-workload-cluster).
1. Without asking Flux to reconcile, it waits up to 150 seconds, two `retryInterval`s and a margin, for the
   organisation's `Kustomization` to get `Ready` on its own retry.

The other checks run after it. The cluster `Kustomization`s are in the organisation's `namespace` directory, so they
appear only once the organisation's `Kustomization` is `Ready`, and run as `org-org-name/automation`.
`tests/ats/test_root_build.py` checks, without a cluster, that the build of `MC_NAME.yaml` holds only `Organization`s
and objects in `default`, and that each organisation's namespace `Kustomization` applies into the organisation's
namespace. The `Kustomization`s it applies have to read the repository's `GitRepository` in `default`, depend on it,
directly or through another of them, and decrypt with a key Secret it applies too.

## The rights of the `automation` ServiceAccounts

A `Kustomization` or `HelmRelease` with `serviceAccountName: automation` runs as the `automation` ServiceAccount of its
namespace, which [rbac-operator](https://github.com/giantswarm/rbac-operator) creates in `default` and in every `org-*`
namespace of a management cluster. The test gives these ServiceAccounts exactly the rights they have there, so an
example that a management cluster would refuse with `Forbidden` fails the test too. The `automation_rbac` fixture in
[tests/ats/automation_rbac.py](../../tests/ats/automation_rbac.py) creates them for `default` once every CRD of the test
is installed, and [the organization-operator stand-in](#the-organization-operator-stand-in) for the organisation's
namespace once it exists, as rbac-operator does for a new organisation namespace. It replaces an existing one whose
rules or subjects differ, as rbac-operator does, and deletes and creates again a binding whose role differs, which the
API server doesn't let it change, as `kubectl auth reconcile` does. `test_automation_access` in
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
not yet released `80aed29e11e49eac3a7f77b601c6df124e66cfe4`, and the `RoleBinding`s
of Giant Swarm's Flux from management-cluster-bases at `52aa8ee8a4ddb0c95e693bac67556150e33d956f` and flux-app at
`02f4e84fa7a585de8e0deb95983ea47a4cbf828c`. [tests/ats/automation_roles.py](../../tests/ats/automation_roles.py) holds the
rules, [tests/ats/automation_bindings.py](../../tests/ats/automation_bindings.py) and
[tests/ats/automation_accounts.py](../../tests/ats/automation_accounts.py) the bindings, and each names the file and
lines each object comes from. rbac-operator builds `read-all` from the API server's discovery, so the test
does too: it covers the resources served when the fixture runs. The test leaves out the binding to Crossplane's
`crossplane-edit`, which rbac-operator creates only where Crossplane runs, and Kyverno policies that limit Flux on a
management cluster. When rbac-operator changes the rights, update the modules and the commits.

## The `out-of-band-no-flux` workload cluster

`WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload cluster, and the cluster's
`HelmRelease`s install their apps there, through the `out-of-band-no-flux-kubeconfig` Secret a management cluster
has for it. The test installs a [vCluster](https://www.vcluster.com/) named `out-of-band-no-flux` in the test
cluster, and [the organization-operator stand-in](#the-organization-operator-stand-in) puts its kubeconfig, with the
vCluster's in-cluster Service as the server, in that Secret once the organisation's namespace exists, so the
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
  [application team](../tutorials/advanced/teams.md) `hello-team-wc`, whose Flux runs in the workload cluster. The
  vCluster runs no Flux: the objects only have to exist.

The vCluster runs CoreDNS, as the apps run pods there.

Every file in `tests/ats/assertions/exists-in-workload-cluster` is verified against the vCluster, the same way as the
files in `tests/ats/assertions/exists`. They list the main workload of each app:

- Every workload-cluster app whose kubeconfig Secret exists needs an assertion of its main workload: an object with a
  `helmRelease: <namespace>/<name>` key naming the `HelmRelease`. The key isn't a field of the object, so the
  comparison skips it. The test fails for a `HelmRelease` without one, so a new app needs an assertion. For
  `gateway-api-crds`, which runs no workload, it's the `gateways.gateway.networking.k8s.io` CRD the chart installs.
- Every `Deployment` in them has to be available, too. That includes the `podinfo` `Deployment` that the
  [application team](../tutorials/advanced/teams.md) `hello-team` delivers from its own repository into its namespace. Its
  `Kustomization` runs as the `automation` ServiceAccount of `org-org-name`, which the organization-operator stand-in
  creates with the rights a Giant Swarm management cluster gives it.
- The `GitRepository` and `Kustomization` of the application team `hello-team-wc` only have to exist, as nothing in
  the vCluster reconciles them.
- The `giantswarm-default` `Gateway` of the `gateway-api-config` app only has to exist. kind has no load balancer for
  its Service, so the `Gateway` can't be `Programmed`. Its `HelmRelease` gets `Ready` all the same.

To run the test on your machine, see [Run the kind test locally](../tutorials/advanced/testing.md#run-the-kind-test-locally):
pytest has to reach the vCluster on the kind node's network.

`tests/ats/conftest.py` pins the `vcluster` chart (`VCLUSTER_CHART_VERSION`, 0.37.6) and the vCluster's Kubernetes
image (`VCLUSTER_KUBERNETES_IMAGE_TAG`, v1.36.6). Keep the image on the Kubernetes minor version of the kind cluster and
the management clusters when you bump either. A vCluster runs as a pod in the kind cluster, so more workload clusters
cost a pod each rather than another kind cluster on the runner. In a [comparison](https://github.com/giantswarm/gitops-template/pull/277)
with a second kind cluster, the vCluster took 29 seconds to set up against 17 (medians of 6 and 15 runs), and the whole
kind job 254 seconds against 237, less than the spread of about 60 seconds between runs of the same setup.

## Kyverno

Kyverno runs on every Giant Swarm management cluster, and the External Secrets Operator chart creates its
`PolicyException`s only when Kyverno's CRDs are there, so the test installs Kyverno before ESO. It installs Giant
Swarm's charts, the ones team Shield ships to the management clusters, from `oci://gsoci.azurecr.io/charts/giantswarm`:
`kyverno-crds` 1.19.2, as the `kyverno` chart leaves the CRDs to it, then `kyverno` 0.26.1, the chart of
`kyverno-app`. Kyverno's pods use the `giantswarm-critical` PriorityClass and its `PolicyException`s go in the
`giantswarm` namespace, which every management cluster has, so the test first installs Giant Swarm's
`priority-classes` 0.3.1 chart and creates the namespace. The charts are pinned in `tests/ats/kyverno_install.py`. [tests/ats/fixtures/kyverno-values.yaml](../../tests/ats/fixtures/kyverno-values.yaml)
turns off the objects whose CRDs the kind cluster doesn't have: the `CiliumNetworkPolicy`s, `PodLogs`,
`VerticalPodAutoscaler`s and `ServiceMonitor`s. It also lowers the background and reports controllers' requests from
the chart's 500m CPU and 1Gi, sized for a management cluster, so that Flux still fits on the single kind node.

## Flux Operator

The [upgrade window examples](../tutorials/advanced/scheduled-upgrades.md) are Flux Operator
`ResourceSetInputProvider`s and `ResourceSet`s, so the test installs Flux Operator before Flux applies the repository.
It installs Giant Swarm's `flux-operator` chart 0.9.0 (Flux Operator v0.62.1), the version management-cluster-bases
deploys, from `oci://gsoci.azurecr.io/charts/giantswarm`, into `flux-giantswarm`. The chart is pinned in
`tests/ats/flux_operator_install.py`. [tests/ats/fixtures/flux-operator-values.yaml](../../tests/ats/fixtures/flux-operator-values.yaml)
has the chart install the CRDs, which a management cluster gets from management-cluster-bases, and turns off the
`VerticalPodAutoscaler` and the `ServiceMonitor`.

A new provider whose window is closed exports no version, so once the `Kustomization`s are `Ready`, the test forces
each example's provider once and waits for its `ResourceSet`, before it checks the sources and `HelmRelease`s. Then:

- `test_schedule_window` checks what `schedule.window` does, on providers of its own.
- `test_scheduled_cluster_upgrade` moves the `scheduled-upgrades` cluster to an older release, then to its range with
  the window closed, where the release has to stay, then opens the window, where it has to move.
- `test_input_loss_keeps_the_app` takes the version of the hello-world example away, by an unreadable registry, a
  range no tag matches and a deleted provider, and checks that the `ResourceSet` waits and the App stays installed.
- `test_input_loss_keeps_the_cluster` does the same to the `scheduled-upgrades` cluster, and then deletes its
  `ResourceSet`. The cluster's `HelmRelease` and `OCIRepository` have to stay each time.

The assertions in `tests/ats/assertions/exists/organizations/workload-clusters/scheduled-upgrades` check that the
cluster's `ResourceSet`, not its `Kustomization`, renders the cluster's `OCIRepository` and `HelmRelease`, with the
protection of the cluster base.

They change the providers with the `Kustomization` that applies them suspended, and resume it afterwards. The
hello-world example's `HelmRelease` for the `out-of-band-no-flux` cluster installs into the vCluster, so it's in
`tests/ats/assertions/exists-in-workload-cluster`; `test_prune` leaves it out of the apps it expects to go with the
cluster's `Kustomization`s, as an organisation's `ResourceSet` installs it.

## Example checks

Some examples get a test of their own, beyond getting `Ready`.

### Shared objects

`test_shared_object_copied` checks the [shared-objects example](../how-to/share-objects.md).
Every organisation whose `namespace/shared-objects` lists the base has to have the `shared-ca-bundle` ConfigMap in its
namespace, with the data of the base in Git, so a change to the base reaches every copy. The test then changes one
copy, asks Flux to reconcile the organisation's namespace `Kustomization`, which applied it, and waits for Flux to put
the copy back.
`tests/ats/test_shared_objects.py` checks, without a cluster, that the example organisation lists the base.

### Workload cluster secret stores

`test_workload_cluster_secret_store` checks the
[workload cluster secret store example](../how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno),
the organisation's Kyverno `Policy`, with the vCluster's kubeconfig Secret, which the test labels and types as Cluster
API does. Kyverno's background controller needs rights in the organisation's namespace that rbac-operator grants on a
management cluster and the example doesn't ship; the organization-operator stand-in creates them with the others, see
[The rights of the `automation` ServiceAccounts](#the-rights-of-the-automation-serviceaccounts). Flux applies the
`Policy` as `default/automation`, and the `default` store reads the organisation's namespace as its `automation`. The
test waits for the organisation's `SecretStore` `default`, `out-of-band-no-flux-eso-cluster-auth` and the
`out-of-band-no-flux-eso-cluster-store` `SecretStore`, then reads a Secret from the vCluster through that store and
checks its value. It then waits for the
[`PushSecret` example](../how-to/workload-cluster-secrets.md#push-a-generated-password) to get Ready and for the
`pushed-password` Secret it writes into the vCluster's `default` namespace to have a `password` of the generator's 32
characters. On a management cluster, the ESO chart's `CiliumNetworkPolicy` lets ESO reach the cluster and the world; the
kind cluster has no Cilium, so the `NetworkPolicy` in `tests/ats/workload_cluster_secrets.py`, which the
[workload cluster secrets example](#workload-cluster-secrets) needs too, gives ESO the same egress. Last, the test
writes a kubeconfig Secret for a new cluster, `new-cluster-kubeconfig`, with the vCluster's kubeconfig, and waits for
the policy to react to it with `new-cluster-eso-cluster-auth` and a Ready `new-cluster-eso-cluster-store` in the
organisation's namespace, then deletes the Secret.

### Workload cluster secrets

The kind test runs the [workload cluster secrets example](../how-to/workload-cluster-secrets.md#push-secrets-through-a-store-in-git)
for real: it creates the test store, and the vCluster stands in for the workload cluster. It checks that both Secrets
are on the management cluster and in the workload cluster. The kind cluster has no Cilium, so a `NetworkPolicy` in
`tests/ats/workload_cluster_secrets.py` gives ESO the egress the chart's `CiliumNetworkPolicy` gives it on a
management cluster; the [workload cluster secret store test](#workload-cluster-secret-stores) relies on it as well.
CI can't reach a cloud secret manager, so `tools/test-all-ff validate` only builds each base in `bases/secret_stores`
and checks it against the schemas of its kinds.
