# Schedule updates in upgrade windows

- [Schedule updates in upgrade windows](#schedule-updates-in-upgrade-windows)
  - [When to use it](#when-to-use-it)
  - [How the examples work](#how-the-examples-work)
  - [Apps on several clusters](#apps-on-several-clusters)
  - [Installing before the first window](#installing-before-the-first-window)
  - [Moving an existing cluster](#moving-an-existing-cluster)
  - [Notes on the examples](#notes-on-the-examples)
  - [What the window does](#what-the-window-does)
  - [Losing the version](#losing-the-version)

This guide holds back the upgrades of an App or a cluster until an upgrade window, with Flux Operator. It builds on
automatic updates, which install a new version as soon as it's published, see
[Enable automatic updates of an existing App](./automatic-updates.md).

A version range upgrades the App as soon as a new version is published, at any time of day. Flux Operator, which runs
on every Giant Swarm management cluster, can hold upgrades back until an upgrade window instead. Its API,
`fluxcd.controlplane.io/v1`, is used as it is:

- a `ResourceSetInputProvider` of type `OCIArtifactTag` lists the tags of the chart, keeps the ones in its
  `spec.filter.semver` range and exports the highest. Its `spec.schedule` decides when it looks.
- a `ResourceSet` renders the App's `OCIRepository` and `HelmRelease` from that version, with
  `<< inputs.tag >>` where the version goes.

## When to use it

A plain `HelmRelease` is enough when:

- a pinned version is fine: every upgrade is a pull request, and it reaches the cluster when it's merged.
- a range is fine: the App may upgrade whenever a new version is published.

Use a `ResourceSetInputProvider` and a `ResourceSet` when upgrades have to wait for a window, for example the release
of a production cluster, or an App that should only restart in working hours. A `ResourceSet` also rolls the same App
out to several workload clusters from one list.

## How the examples work

- [multicluster/apps/hello-world-scheduled](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/apps/hello-world-scheduled/resource-set.yaml)
  installs hello-world on the workload clusters in
  [multicluster/apps/clusters.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/apps/clusters.yaml).
  Its provider picks the highest release below `4.0.0` from Monday to Thursday, 09:00 to 17:00 in Berlin. With
  `inputStrategy: Permute`, the `ResourceSet` renders an `OCIRepository` and a `HelmRelease` for every cluster at that
  version, see [Apps on several clusters](#apps-on-several-clusters).
- [WC_NAME_SCHEDULED_UPGRADES](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/cluster/cluster-resource-set.yaml)
  is a cluster whose Giant Swarm release moves to the highest `v36` release only on Tuesdays, 02:00 to 05:00 UTC. Its
  `ResourceSet` renders the whole cluster, the `OCIRepository` and the `HelmRelease` as the cluster base has them, at
  the version its provider picks; a patch drops the base's two. The base and the region component still give the
  cluster its values, and the `HelmRelease` lists the region's values itself, as a component's patch doesn't reach into
  a `ResourceSet`. A new major release is a change to the range in Git, and an exact version in the range pins the
  cluster to it. Like a new release, a change to the range reaches the cluster at the next window, or at once when you
  force the provider, see below.

Both examples set the `metadata.namespace` of the objects their `ResourceSet` renders explicitly, to their provider's:
`<< inputs.provider.namespace >>`, or `<< inputs.hello_world_scheduled_version.provider.namespace >>` with `Permute`.
A `HelmRelease`'s `chartRef` needs none: Flux looks for the `OCIRepository` in the `HelmRelease`'s namespace.

## Apps on several clusters

An organisation's apps that roll out to several of its workload clusters live in `multicluster/apps`, one directory and
one `ResourceSet` per app. The management cluster's Kustomization doesn't apply them: it creates the Flux
`Kustomization` `MC_NAME-multicluster-apps-ORG_NAME`, in `multicluster/apps.yaml`, and that one applies
`multicluster/apps`, with `${organization}` substituted.

The clusters are listed once, in `multicluster/apps/clusters.yaml`. `multicluster/apps/kustomization.yaml` applies it as
a patch to every `ResourceSet` in the directory, and sets their `spec.inputs`:

```yaml
spec:
  inputs:
    - cluster: out-of-band-no-flux
    - cluster: out-of-band-flux-app
```

To roll every app out to a new cluster, add its name to `clusters.yaml`. That's enough only when the cluster has what
each app depends on, see below. Removing a name uninstalls the apps from that
cluster. With `Permute`, a `ResourceSet` reads the name as `inputs.<its name>.cluster`, with `_` for `-`, such as
`inputs.hello_world_scheduled.cluster`. To give one app a list of its own, add a patch after `clusters.yaml` in
`kustomization.yaml` that targets that `ResourceSet` by name and sets its `spec.inputs`.

A listed cluster may not exist or be ready yet. The example app's `HelmRelease` doesn't install early: hello-world has
the cluster's `gateway-api-crds` release in `dependsOn`, which only gets ready once the cluster is up, and
helm-controller retries until then. That dependency is the example app's own, and needs envoy-gateway on that cluster:
on a cluster without it, hello-world stays `DependencyNotReady` while the `Kustomization` and the `ResourceSet` report
`Ready`. Nothing fails meanwhile: the `ResourceSet` applies the `HelmRelease` without waiting for it, and the
`Kustomization` applies only the `ResourceSet` and its `ResourceSetInputProvider`. Unlike a cluster's apps
Kustomization, it doesn't wait for the Cluster API `Cluster` to be `Available`: a `HelmRelease` can only depend on other
`HelmRelease`s, so an app without such a dependency would only wait for the cluster's kubeconfig `Secret`, and fail and
retry until it exists.

## Installing before the first window

A new provider whose window is closed reports `Ready` but exports no version until the window opens. Until then its
`ResourceSet` waits, so the App isn't installed and the cluster isn't created. To install at once, force the provider
once, after Flux has applied it. It then reads the registry outside its schedule, this one time:

```sh
# the hello-world example
flux-operator reconcile inputprovider hello-world-scheduled-version -n org-${ORG_NAME} --force
# the WC_NAME_SCHEDULED_UPGRADES example: its provider is named after the cluster
flux-operator reconcile inputprovider ${CLUSTER_NAME}-release -n org-${ORG_NAME} --force
```

Without the `flux-operator` CLI, set both annotations to the same new value:

```sh
now="$(date +%s)"
kubectl annotate resourcesetinputprovider ${CLUSTER_NAME}-release -n org-${ORG_NAME} --overwrite \
  reconcile.fluxcd.io/requestedAt="${now}" reconcile.fluxcd.io/forceAt="${now}"
```

Later upgrades still wait for the window. The comments in both examples' providers and `ResourceSet`s give the same
step, and the kind test does the same for both examples.

## Moving an existing cluster

A cluster that the cluster base creates can move to the layout of `WC_NAME_SCHEDULED_UPGRADES`. Its `OCIRepository` and
`HelmRelease` leave its `Kustomization`, which doesn't delete them, as both have the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation, and its `ResourceSet` takes them over once its provider has a
version. Forcing the provider picks the highest release in the range at once, outside the window, so pin the range to
the release the cluster runs first:

1. Wait until Flux has applied the updated cluster base, so that the cluster's live `OCIRepository` has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. Without it, the move tries to prune the `OCIRepository`,
   which the `giantswarm.io/prevent-deletion` label refuses, and the prune fails.
1. Set the provider's `spec.filter.semver` to the cluster's current release, the `release` in its `Kustomization`, for
   example `'36.2.0'`. Move the cluster's files to the example's layout, then commit and push.
1. Once Flux has applied the provider, force it as above. The `ResourceSet` takes over the `OCIRepository` and the
   `HelmRelease` at the release the cluster already runs, so the cluster doesn't change.
1. Set the range back, for example to `'>=36.0.0 <37.0.0'`, then commit and push. The cluster moves to the highest
   release in it at the next window.

## Notes on the examples

Keep one `ResourceSet` per App, as the example does: a `ResourceSet` deletes what it rendered for an input that has
gone, so Apps that shared one would go together. Set `spec.filter.limit: 1`, or every exported tag becomes a release
of its own. The `ResourceSet`s run as the organization's `automation` service account, in `spec.serviceAccountName`:
Flux Operator applies what they render with that account's permissions, and a Kyverno policy on the management
clusters rejects a `ResourceSet` without one. The `ResourceSet` and its provider have to be in the same namespace.

To see which version a provider picked, and when it looks next:

```sh
kubectl get resourcesetinputproviders -n org-${ORG_NAME} \
  -o 'custom-columns=NAME:.metadata.name,VERSION:.status.exportedInputs[0].tag,NEXT:.status.nextSchedule.when'
```

## What the window does

The kind test checks what follows, in `tests/ats/resource_set_schedule.py`.

With a `window`, the provider looks at the registry only while the window is open: from the `cron` time, in its
`timeZone`, for the length of the window, less the provider's timeout of two minutes. Inside the window it looks every
10 minutes. Outside it, nothing moves the version: not a new release, and not a change to the range in Git either.
Both wait for the next window. A window has to be at least twice the timeout, so at least `4m`.

`window` defaults to `0s`, which Flux Operator's API documents as "no window is applied". That doesn't turn the
schedule off, and it doesn't hold upgrades back either: the provider looks at the `cron` time, and also whenever
something asks it to, such as a change to its spec or a restart of Flux Operator. It only stops looking every 10
minutes. Set a `window` to keep upgrades in the window.

## Losing the version

Without a version, a `ResourceSet` renders nothing and deletes what it rendered before, which uninstalls the App or
deletes the cluster. The version goes when no tag matches the range, when the registry can't be read or when the
provider is deleted. Both examples guard against it with a `dependsOn` on their provider:

```yaml
dependsOn:
  - apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    name: hello-world-scheduled-version
    namespace: org-${organization}
    ready: true
    readyExpr: >-
      status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
      && has(status.exportedInputs)
```

Until the provider is `Ready` with a version, the `ResourceSet` reports `DependencyNotReady` and leaves what it
rendered as it is. The cluster's `OCIRepository` and `HelmRelease` also have the `fluxcd.controlplane.io/prune:
disabled` annotation, so the `ResourceSet` never deletes them, not even when the `ResourceSet` itself is deleted or its
file is deleted from Git, and the `giantswarm.io/prevent-deletion` label, as in the cluster base. The kind test takes
the version away in each of the three ways and checks that the App stays installed, in
`tests/ats/resource_set_guard.py`, and that the cluster's `HelmRelease` and `OCIRepository` stay, also when the
`ResourceSet` is deleted, in `tests/ats/resource_set_cluster_guard.py`.
