# How it works

This repository describes your workload clusters and the apps on them as files in Git. Flux, which runs on every Giant
Swarm management cluster, reads the repository and applies it. To create a cluster, you add a few files and push them.
To change it, you change those files and push again. Git keeps the history of every change, and a pull request is
the review before it reaches a cluster.

This page explains what happens between a `git push` and a running cluster, and why the repository is cut up the way it
is. For the steps, see the [basic tutorial](../tutorials/basic/getting-started.md).

## From a commit to a cluster

Take a cluster named `demowc` in the organisation `demoorg`, on the management cluster `demomc`. Its files live in
`management-clusters/demomc/organizations/demoorg/workload-clusters/demowc/`, and its Flux `Kustomization`s, such as
`demowc.yaml`, next to it in `workload-clusters/`.

Think of it as a relay. Each Flux `Kustomization` runs one leg, then hands the baton to the ones it created:

1. You push a commit. A Flux `GitRepository` on the management cluster fetches it.
1. The management cluster's own Flux `Kustomization`, `demomc.yaml`, applies everything under
   `management-clusters/demomc` that goes in `default`, and the `Organization`s. It leaves out everything that goes in
   an organisation's namespace, so it works on a new management cluster, where the `org-demoorg` namespace doesn't
   exist yet: organization-operator creates it for the `Organization`.
1. Among what `demomc.yaml` applies is the organisation's own `Kustomization`, `namespace.yaml`. It applies what
   `organizations/demoorg/namespace` lists into `org-demoorg`. It fails until the namespace exists, and succeeds on its
   next retry. Its `dependsOn` names `demomc.yaml`'s `Kustomization`, so `demomc.yaml` always applies a commit first.
1. `namespace/kustomization.yaml` lists `../workload-clusters`, so `namespace.yaml` applies the Flux `Kustomization`
   of each workload cluster listed in `workload-clusters/kustomization.yaml`, such as `demowc.yaml`, into
   `org-demoorg`. A cluster file that isn't in that list does nothing. It stops there and doesn't apply what's inside
   the `demowc` directory. The cluster's `Kustomization`s depend on `namespace.yaml`'s, so it applies a commit before
   them.
1. The `demowc.yaml` Kustomization applies the `demowc/cluster` directory, as the `automation` ServiceAccount of
   `org-demoorg`. While it does, it fills in variables such as `${cluster_name}`, `${organization}` and `${release}`
   from its own settings.
1. `cluster` holds the cluster: a Flux `OCIRepository` for its chart, for example `release-aws`, and a Flux
   `HelmRelease` that installs it on the management cluster. The chart creates the cluster with Cluster API. When the
   cluster is up, the management cluster also creates the `demowc-kubeconfig` Secret, with access to the new cluster,
   and the `demowc-cluster-values` ConfigMap, with values apps can use, such as the cluster's base domain.
1. `apps` holds the apps. Each app is a Flux `OCIRepository`, which points at a chart in an OCI registry, and a Flux
   `HelmRelease`, which installs it. Both stay on the management cluster, in the `org-demoorg` namespace. The
   `HelmRelease` uses the `demowc-kubeconfig` Secret to install the chart into the workload cluster. A second
   Kustomization, `demowc-apps.yaml`, applies `apps` once `demowc.yaml` is `Ready`, which is when Cluster API reports
   the cluster's control plane available and reachable.

[Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations) has the details of each leg: the fields,
the order and what happens when one of them fails.

Flux keeps doing this. When a file changes in Git, it applies the change. When someone changes a field that Git sets
on an object a Flux `Kustomization` applies, such as a `HelmRelease` or a values ConfigMap on the management cluster,
Flux sets it back at its next run. Fields added by hand stay.

What a chart installs in a workload cluster is another matter. helm-controller installs and upgrades it, and by default
doesn't look at it again until the next upgrade, so a `kubectl edit` on an app's Deployment stays until the chart or
its values change. [Correct changes made by hand](../how-to/update-app.md#correct-changes-made-by-hand) shows how to
have helm-controller set those back as well, and what it costs.

The Kustomizations in this repository have `prune: true`. When you delete a file in Git, or take it out of a
`kustomization.yaml`, Flux deletes what the file created at its next run. Delete an app's directory and Flux deletes its
`HelmRelease`, which uninstalls the app from the workload cluster. That's what you want for an app, and exactly what
you don't want for a cluster or an organisation, so the objects whose deletion would take a cluster with them are
protected, see [Deletion protection](./deletion-protection.md).

Why the relay, rather than one `Kustomization` that applies everything? Each leg has its own job, its own rights and
its own failures:

- The management cluster's `Kustomization` creates the organisations and the namespaces' `Kustomization`s. It works
  before any organisation's namespace exists, and it never waits for an organisation.
- Each organisation's `namespace.yaml` lives in `default` and runs as `default/automation`. It applies the
  organisation's `namespace` directory into the organisation's namespace with `targetNamespace`, and a mistake in one
  organisation's `namespace` directory stops only that organisation. The organisation's top-level files, such as
  `namespace.yaml` itself, are in the management cluster's `Kustomization`, so a mistake there stops every
  organisation until it's fixed.
- Each cluster gets its own `Kustomization`s, with its own variables, so one base works for every cluster, and a
  mistake in one cluster's directory doesn't stop the others. They live in the organisation's namespace and run as
  `org-<organisation>/automation`, which may write only in that namespace, so one organisation's clusters can't
  touch another's. Splitting a cluster's `Kustomization` in two lets the apps wait for the cluster.

Everything in `cluster` and `apps` is a resource on the management cluster that configures the workload cluster.
Resources that must be applied inside the workload cluster directly go into an optional `out-of-band` directory next
to them, which the cluster's `kustomization.yaml` leaves out. A third Kustomization, such as `demowc-direct.yaml`,
applies it with the `demowc-kubeconfig` Secret, or Flux runs in the workload cluster and reads it there, see
[Apply resources straight to a workload cluster](../tutorials/advanced/out-of-band.md).

## Bases and variables

Most clusters and apps look alike. The `bases` directory holds what they share, so a cluster's own files stay short:

- `bases/clusters` holds the cluster bases. A provider's base is named after the provider: for example,
  `bases/clusters/capa` installs the `release-aws` chart, whose version is the Giant Swarm release. A cluster base built
  on it sits next to it, see [Share cluster defaults](../tutorials/intermediate/cluster-bases.md).
- `bases/apps` has App Templates: an app with its default values, ready to deploy to many clusters, see
  [Reuse an app's configuration](../tutorials/intermediate/app-templates.md).
- `bases/stacks` has stacks: several apps deployed together that may depend on each other, such as
  `bases/stacks/hello-web`, see [Deploy several apps together](../tutorials/intermediate/stacks.md).
- `bases/environments` has the stages and regions a cluster adds as components, see
  [Stages and regions](../tutorials/intermediate/stages-and-regions.md).

A cluster's directory points at bases in its `kustomization.yaml` and only adds what's different, such as its own
values. The bases use variables like `${cluster_name}` where every cluster needs its own name. The cluster's Flux
`Kustomization` sets them in `spec.postBuild.substitute`, so one base works for every cluster.
[Variables](../reference/repo-structure.md#variables) lists them.

For example, a cluster made from the CAPA cluster base needs only this `kustomization.yaml` in `cluster`, plus the
`cluster_description`, `cluster_name`, `organization` and `release` variables in its Flux `Kustomization`. The
component sets the cluster's region, which every cluster needs:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
components:
  - ../../../../../../../bases/environments/regions/eu_central
resources:
  - ../../../../../../../bases/clusters/capa
```

To upgrade the cluster, you change `release` and push.

Each layer, the base, the region, a stage and the cluster itself, adds its values as a ConfigMap in the
`HelmRelease`'s `valuesFrom`, and Flux merges them in order. [Values](../reference/values.md) lists the layers and the
rules. Why some layers are bases and others components is in [Composition](./composition.md).

## Base apps and secondary apps

An app goes into one of two directories of the cluster, and the choice decides when it installs.

A base app is one the cluster needs from the start, such as the Gateway API charts of the envoy-gateway stack in the
out-of-band examples. It goes into `cluster/apps`, and the cluster's `Kustomization`, `WC_NAME.yaml`, applies it with
the cluster. Its `HelmRelease` exists before the cluster does, fails while there's no kubeconfig Secret, and installs as
soon as the cluster can take it.

A secondary app goes into `apps`, which the cluster's apps `Kustomization`, `WC_NAME-apps.yaml`, applies once the
cluster's control plane is up, because its `dependsOn` waits for the cluster's `Kustomization`. Most apps are
secondary. On a new cluster they start installing as soon as the control plane is up, which can be before any worker
node has joined: their pods wait `Pending`, and a `HelmRelease` may run out its 10-minute `timeout`, be uninstalled and
installed again, up to 10 times. It settles by itself once the nodes join. That's the price of not waiting for every
node pool, which would hold back every later change to the apps while one node pool is short.

Both kinds are the same files, an `OCIRepository` and a `HelmRelease`, in a directory of their own. To move an app from
one kind to the other, move its directory and its entry in the `kustomization.yaml` that lists it, see
[Make it a base app](../how-to/add-app.md#make-it-a-base-app).

## Next steps

- The [basic tutorial](../tutorials/basic/getting-started.md) creates a cluster with an app, step by step.
- [Secrets](./secrets.md) explains where the repository's secrets come from.
- [Repository structure](../reference/repo-structure.md) lists every directory and file, and the rules for naming
  them.
