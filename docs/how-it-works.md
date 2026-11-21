# How it works

This repository describes your workload clusters and the apps on them as files in Git. Flux, which runs on every Giant
Swarm management cluster, reads the repository and applies it. To create a cluster, you add a few files and push them.
To change it, you change those files and push again. Git keeps the history of every change, and a pull request is
the review before it reaches a cluster.

This page explains what happens between a `git push` and a running cluster. For the steps, see
[Getting started](./getting-started.md).

## From a commit to a cluster

Take a cluster named `demowc` in the organization `demoorg`, on the management cluster `demomc`. Its files live in
`management-clusters/demomc/organizations/demoorg/workload-clusters/`.

1. You push a commit. A Flux `GitRepository` on the management cluster fetches it.
1. The management cluster's own Flux `Kustomization`, `demomc.yaml`, applies everything under
   `management-clusters/demomc`: the organizations, and the Flux `Kustomization` of each workload cluster listed in
   `workload-clusters/kustomization.yaml`, such as `demowc.yaml`. A cluster file that isn't in that list does
   nothing. It stops there and doesn't apply what's inside the `demowc` directory. It applies only objects in
   `default` and the `Organization`s, so it works on a new management cluster, where the `org-demoorg` namespace
   doesn't exist yet: organization-operator creates it for the `Organization`. What the organisation keeps in its
   namespace is in `organizations/demoorg/namespace`, which the organisation's own `Kustomization`, `namespace.yaml`,
   applies into `org-demoorg`. That one fails until the namespace exists, and succeeds on its next retry. See
   [Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations).
1. The `demowc.yaml` Kustomization applies the `demowc/cluster` directory. While it does, it fills in variables
   such as `${cluster_name}`, `${organization}` and `${release}` from its own settings.
1. `cluster` holds the cluster: a Flux `OCIRepository` for its chart, for example `release-aws`, and a Flux
   `HelmRelease` that installs it on the management cluster. The chart creates the cluster with Cluster API. When the
   cluster is up, the management cluster also creates the `demowc-kubeconfig` Secret, with access to the new cluster,
   and the `demowc-cluster-values` ConfigMap, with values apps can use, such as the cluster's base domain. Base apps,
   the ones the cluster needs from the start, sit next to it in `cluster/apps` and install with it.
1. `apps` holds the other apps. Each app is a Flux `OCIRepository`, which points at a chart in an OCI registry,
   and a Flux `HelmRelease`, which installs it. Both stay on the management cluster, in the `org-demoorg` namespace.
   The `HelmRelease` uses the `demowc-kubeconfig` Secret to install the chart into the workload cluster. These apps
   wait for the cluster: a second Kustomization, `demowc-apps.yaml`, applies `apps` once `demowc.yaml` is `Ready`,
   which is when Cluster API reports the cluster `Available`. See
   [Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations).

Flux keeps doing this. When a file changes in Git, it applies the change. When someone changes a field that Git sets,
Flux sets it back at its next run. Fields added by hand stay.

The Kustomizations in this repository have `prune: true`. When you delete a file in Git, or take it out of a
`kustomization.yaml`, Flux deletes what the file created at its next run. For example, delete an app's directory and
Flux deletes its `HelmRelease`, which uninstalls the app from the workload cluster, and its `OCIRepository` and
ConfigMaps. When you take a cluster's `Kustomization` out of `workload-clusters/kustomization.yaml`, Flux deletes it
together with everything it applied, except the objects below.

Some objects delete a whole cluster when they go, so they carry two markers:

- The `kustomize.toolkit.fluxcd.io/prune: disabled` annotation: Flux doesn't delete them, even when their files
  disappear from what it renders, for example because a mistake in a template drops them.
- The `giantswarm.io/prevent-deletion: "true"` label: the `kyverno-policies-ux` policies on a Giant Swarm management
  cluster refuse to delete them, whoever asks, `kubectl` and Flux included, until the label is removed.

The protected objects are:

- The cluster's `HelmRelease`, in `bases/clusters/capa/template`. Deleting it uninstalls the chart, and Cluster API
  then deletes the cluster and its cloud infrastructure. The base also puts the annotation and the label on the
  cluster's `OCIRepository`, so that the `HelmRelease` keeps its chart, and sets `global.metadata.preventDeletion` so
  that the chart puts the label on the `Cluster`.
- The `Organization`, such as `organizations/demoorg/demoorg.yaml`. Deleting it deletes the `org-demoorg` namespace,
  with every cluster in it. Its file can't go on its own anyway: the organisation's `kustomization.yaml` takes the
  organisation's name from it, so without it the management cluster's Kustomization fails to build, and applies and
  prunes nothing until the file is back.
- The SOPS key `Secret`s in `secrets/`, such as `sops-gpg-master`, and in an organisation's `namespace/secrets/`, such
  as a `-direct` `Kustomization`'s key. Flux decrypts with them, so deleting one stops GitOps for every cluster that
  uses it. The keys are encrypted, so each directory's `kustomization.yaml` adds the annotation and the label instead:
  changing an encrypted file by hand breaks its SOPS checksum.

When you delete their files, they stay on the management cluster and the cluster keeps running, but Flux no longer
manages them. A cluster `HelmRelease` that stays without its ConfigMaps can't reconcile, and reports it as not ready.
To delete the cluster, remove the labels with a push first, then delete its `HelmRelease` and its `OCIRepository` by
hand, see [Delete the cluster](./getting-started.md#6-delete-the-cluster-optional).

The rest of the cluster's objects, such as its values ConfigMaps and its apps, don't delete the cluster, so Flux
deletes them. Add the annotation and the label to anything else
that must outlive its file, such as the cluster `HelmRelease` and `OCIRepository` of a cluster base you write yourself:
without them on the `OCIRepository`, Flux deletes it and the `HelmRelease` it keeps loses its chart. `kubectl gs`
doesn't add them yet: add them by hand to the `Organization` that `kubectl gs gitops add organization` writes, and to
the cluster `HelmRelease` and `OCIRepository` of a base that `kubectl gs gitops add base` writes.

The split between the two kinds of Kustomization matters. The management cluster's Kustomization creates the
cluster's Kustomizations, and they apply the cluster's directory. Each cluster gets its own
variables, and a mistake in one cluster's directory doesn't stop the others.

Everything in `cluster` and `apps` is a resource on the management cluster that configures the
workload cluster. Resources that must be applied inside the workload cluster directly go into an optional
`out-of-band` directory next to them, which the cluster's `kustomization.yaml` leaves out. A third Kustomization,
such as `demowc-direct.yaml`, applies it with the `demowc-kubeconfig` Secret. It lives with that Secret in
`org-demoorg`, so it's in the organisation's `namespace/workload-clusters`. You can also run Flux in the workload
cluster and point it at that directory.

## Bases and variables

Most clusters and apps look alike. The `bases` directory holds what they share, so a cluster's own files stay short:

- `bases/clusters` holds the cluster bases, grouped by provider. For example, `bases/clusters/capa/template`
  installs the `release-aws` chart, whose version is the Giant Swarm release.
- `bases/apps` has App Templates: an app with its default values, ready to deploy to many clusters.
- `bases/stacks` has stacks: several apps deployed together that may depend on each other, such as
  `bases/stacks/hello-web`, see [Stacks](./guides/stacks.md).
- `bases/cluster_templates` and `bases/environments` combine these into clusters for stages like dev and production,
  or for regions.

A cluster's directory points at bases in its `kustomization.yaml` and only adds what's different, such as its own
values. The bases use variables like `${cluster_name}` where every cluster needs its own name. The cluster's Flux
`Kustomization` sets them in `spec.postBuild.substitute`, so one base works for every cluster. The bases use these
variables:

| Variable | What it's for |
| --- | --- |
| `cluster_name` | The workload cluster's name. It names the cluster's resources and its apps, such as `${cluster_name}-hello-world`, and the `<cluster>-kubeconfig` Secret and `<cluster>-cluster-values` ConfigMap the apps read. |
| `organization` | The organisation the cluster belongs to. Its resources go into the `org-${organization}` namespace, and `bases/clusters/capa/template` sets it as `global.metadata.organization` in the chart values. The organisation's `kustomization.yaml` updates it to the name of its `Organization`, see [The organisation's name](./reference/repo-structure.md#the-organisations-name). |
| `release` | The Giant Swarm release the cluster runs: the version of the `release-aws` chart in `bases/clusters/capa/template`. |
| `cluster_description` | A free-text description of the cluster, set as `global.metadata.description` by `bases/clusters/capa/template`. |

Set every variable the cluster's bases use. Flux replaces a variable that isn't set with an empty string; CI fails on
it instead, see [CI validation](./guides/ci-validation.md). CI reads only `spec.postBuild.substitute`, not
`spec.postBuild.substituteFrom`, so a variable set only in `substituteFrom` fails CI, although Flux sets it on the
cluster.

For example, a cluster made from the CAPA cluster base needs only this `kustomization.yaml` in `cluster`, plus the
`cluster_description`, `cluster_name`, `organization` and `release` variables in its Flux `Kustomization`. The
component sets the cluster's region, which every cluster needs, see [Regions](./guides/environments.md#regions):

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
components:
  - ../../../../../../../bases/environments/regions/eu_central
resources:
  - ../../../../../../../bases/clusters/capa/template
```

To upgrade the cluster, you change `release` and push.

## Secrets

Clusters and apps need secrets, such as an app's passwords. There are two ways to handle them:

- Keep them in a secret manager. External Secrets Operator runs on every management cluster and copies them into
  Kubernetes Secrets. The repository only holds `ExternalSecret` resources that say which secret goes where.
  [Getting started](./getting-started.md) uses this way. ESO can also make secrets, such as passwords, and push
  secrets into a new workload cluster, see [Push secrets into a new Workload
  Cluster](./guides/workload-cluster-secrets.md).
- Keep them in the repository, encrypted with [SOPS](https://github.com/getsops/sops) and GPG keys. Flux decrypts
  them when it applies them. [Getting started with SOPS](./getting-started-sops.md) uses this way.

## Next steps

- [Getting started](./getting-started.md) creates a cluster with an app, step by step.
- [Guides](./guides/README.md) cover templates, environments and managing apps.
- [Repository structure](./reference/repo-structure.md) lists every directory and file, and the rules for naming them.
