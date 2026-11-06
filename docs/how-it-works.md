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
   nothing. It stops there and doesn't apply what's inside the `demowc` directory.
1. The `demowc.yaml` Kustomization applies the `demowc/mapi` directory. While it does, it fills in variables such as
   `${cluster_name}`, `${organization}` and `${release}` from its own settings.
1. `mapi/cluster` holds the cluster App. The management cluster installs its chart, for example `release-aws`, and
   the chart creates the cluster with Cluster API. When the cluster is up, the management cluster also creates the
   `demowc-kubeconfig` Secret, with access to the new cluster, and the `demowc-cluster-values` ConfigMap, with values
   apps can use, such as the cluster's base domain.
1. `mapi/apps` holds the apps. Each app is a Flux `OCIRepository`, which points at a chart in an OCI registry, and a
   Flux `HelmRelease`, which installs it. Both stay on the management cluster, in the `org-demoorg` namespace. The
   `HelmRelease` uses the `demowc-kubeconfig` Secret to install the chart into the workload cluster.

Flux keeps doing this. When a file changes in Git, it applies the change. When someone changes a field that Git sets,
Flux sets it back at its next run. Fields added by hand stay.

Note that the Kustomizations in this repository have `prune: false`. Deleting a file in Git doesn't delete the
resource from the cluster, so a mistake can't delete a cluster. To remove something, delete it by hand too.

The split between the two Kustomizations matters. The management cluster's Kustomization creates the cluster's
Kustomization, and the cluster's Kustomization applies the cluster's `mapi` directory. Each cluster gets its own
variables, and a mistake in one cluster's directory doesn't stop the others.

`mapi` stands for Management API. Everything in it is a resource on the management cluster that configures the
workload cluster. Resources that must be applied inside the workload cluster directly go into an optional
`out-of-band` directory next to it. A third Kustomization, such as `demowc-direct.yaml`, applies it with the
`demowc-kubeconfig` Secret. You can also run Flux in the workload cluster and point it at that directory.

## Bases and variables

Most clusters and apps look alike. The `bases` directory holds what they share, so a cluster's own files stay short:

- `bases/clusters` holds the cluster bases, grouped by provider. For example, `bases/clusters/capa/release` is a
  cluster App with the `release-aws` chart, whose version is the Giant Swarm release.
- `bases/apps` has App Templates: an app with its default values, ready to deploy to many clusters.
- `bases/app_sets` groups apps that you deploy together.
- `bases/cluster_templates` and `bases/environments` combine these into clusters for stages like dev and production,
  or for regions.

A cluster's directory points at bases in its `kustomization.yaml` and only adds what's different, such as its own
values. The bases use variables like `${cluster_name}` where every cluster needs its own name. The cluster's Flux
`Kustomization` sets them, so one base works for every cluster.

For example, a cluster made from the release base needs only this `kustomization.yaml` in `mapi/cluster`, plus the
`cluster_description`, `cluster_name`, `organization` and `release` variables in its Flux `Kustomization`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../../../../../../bases/clusters/capa/release
```

To upgrade the cluster, you change `release` and push.

## Secrets

Clusters and apps need secrets, such as an app's passwords. There are two ways to handle them:

- Keep them in a secret manager. External Secrets Operator runs on every management cluster and copies them into
  Kubernetes Secrets. The repository only holds `ExternalSecret` resources that say which secret goes where.
  [Getting started](./getting-started.md) uses this way.
- Keep them in the repository, encrypted with [SOPS](https://github.com/getsops/sops) and GPG keys. Flux decrypts
  them when it applies them. [Getting started with SOPS](./getting-started-sops.md) uses this way.

## Next steps

- [Getting started](./getting-started.md) creates a cluster with an app, step by step.
- [Guides](./guides/README.md) cover templates, environments and managing apps.
- [Repository structure](./repo_structure.md) lists every directory and file, and the rules for naming them.
