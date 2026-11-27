# Deletion protection

GitOps makes deleting things cheap: delete a file, push, and Flux deletes what it made. For an app that's exactly
right. For a workload cluster it's pruning the roses with a chainsaw: one careless `git rm`, or a template that
quietly stops rendering a file, and Flux takes the cluster down with its cloud infrastructure. This page explains
what keeps clusters, organisations and keys from being deleted by accident, and what it takes to delete them on
purpose.

## Prune and prevent-deletion

The Flux `Kustomization`s in this repository have `prune: true`. When you delete a file in Git, or take it out of a
`kustomization.yaml`, Flux deletes what the file created at its next run. Delete an app's directory and Flux deletes
its `HelmRelease`, which uninstalls the app from the workload cluster, and its `OCIRepository` and ConfigMaps. When you
take a cluster's `Kustomization` out of `workload-clusters/kustomization.yaml`, Flux deletes it together with
everything it applied, except the objects below. Without `prune`, Flux would leave behind whatever you delete from Git,
and the repository would stop describing what runs.

Some objects delete a whole cluster when they go, so they carry two markers:

- The `kustomize.toolkit.fluxcd.io/prune: disabled` annotation: Flux doesn't delete them, even when their files
  disappear from what it renders, for example because a mistake in a template drops them.
- The `giantswarm.io/prevent-deletion: "true"` label: the `kyverno-policies-ux` policies on a Giant Swarm management
  cluster refuse to delete them, whoever asks, `kubectl` and Flux included, until the label is removed. The policy
  covers a `HelmRelease` and an `OCIRepository` in `kyverno-policies-ux` 0.16.0 and newer; with an older one, the
  label on the cluster's `HelmRelease` and `OCIRepository` stops nothing.

The two do different jobs. The annotation keeps Flux from trying, so a pruned file doesn't turn into a failing
`Kustomization`. The label stops everyone else, including a person with `kubectl delete` and the wrong context. You
need both: the annotation alone leaves the object open to a manual delete, and the label alone makes Flux fail on
every reconciliation while it tries to prune what it can't.

When you delete the files of a protected object, it stays on the management cluster and the cluster keeps running,
but Flux no longer manages it. A cluster `HelmRelease` that stays without its ConfigMaps can't reconcile, and reports
it as not ready. To delete it on purpose, remove the label with a push first, then delete it by hand, see
[Delete a workload cluster](../how-to/delete-cluster.md).

## The protected objects

- The cluster's `HelmRelease`, in `bases/clusters/capa`. Deleting it uninstalls the chart, and Cluster API
  then deletes the cluster and its cloud infrastructure. The base also puts the annotation and the label on the
  cluster's `OCIRepository`, so that the `HelmRelease` keeps its chart, and sets `global.metadata.preventDeletion` so
  that the chart puts the label on the `Cluster`. Its install remediation is off,
  `install.remediation.remediateLastFailure: false`: Flux remediates a failed install by uninstalling it, which would
  delete the cluster it was installing. Its upgrade remediation is off too: a rollback goes back to the Giant Swarm
  release the cluster had, which rolls its nodes a second time.
- The `Organization`, such as `organizations/demoorg/demoorg.yaml`. Deleting it deletes the `org-demoorg` namespace,
  with every cluster in it. Its file can't go on its own anyway: the organisation's `kustomization.yaml` takes the
  organisation's name from it, so without it the management cluster's `Kustomization` fails to build, and applies and
  prunes nothing until the file is back.
- The SOPS key `Secret`s in the management cluster's `secrets/`, such as `sops-gpg-master`, and in an organisation's
  `namespace/secrets/`, such as a workload cluster's key. Flux decrypts with them, so deleting one stops GitOps for
  every cluster that uses it. The keys are encrypted, so each directory's `kustomization.yaml` adds the annotation and
  the label instead: changing an encrypted file by hand breaks its SOPS checksum.
- The `Kustomization`s that everything else hangs off: the management cluster's own, in `MC_NAME.yaml`, and each
  organisation's namespace `Kustomization`, in `namespace.yaml`, and multicluster apps `Kustomization`, in
  `multicluster/apps.yaml`. These carry the annotation only. When Flux prunes a `Kustomization`, its finalizer
  deletes everything it applied, and the `Kustomization`s among that do the same, all the way down. So a rename, a
  dropped line in a `kustomization.yaml` or a `git rm` of an organisation's directory would uninstall every app on
  every cluster of the organisation, or of the management cluster, and remove their values and secrets. The clusters
  would keep running, empty. The management cluster's `Kustomization` applies itself, so a rename would make it prune
  itself. With the annotation, Flux leaves the `Kustomization` where it is; with its path gone, it fails to build and
  prunes nothing.

The rest of the cluster's objects, such as its values ConfigMaps and its apps, don't delete the cluster, so Flux
deletes them. Add the annotation and the label to anything else that must outlive its file, such as the cluster
`HelmRelease` and `OCIRepository` of a cluster base you write yourself: without them on the `OCIRepository`, Flux
deletes it and the `HelmRelease` it keeps loses its chart.

The cluster's own `Kustomization`s don't have the annotation: deleting them is how you remove a cluster's apps, see
[Delete a workload cluster](../how-to/delete-cluster.md).

Removing an organisation on purpose takes a little longer than deleting its directory, which is the point:

1. Delete its clusters first, as [Delete a workload cluster](../how-to/delete-cluster.md) describes. Otherwise the
   last step uninstalls their apps and leaves the clusters running, empty: their `HelmRelease`s stay whatever happens.
1. Take the annotation off `namespace.yaml` and `multicluster/apps.yaml`, and push. Flux now manages them like any
   other object.
1. Delete the organisation's directory, and push. Flux deletes the two `Kustomization`s and what they applied,
   except the keys. The `Organization` stays, with its own annotation and label: delete it by hand once you've pushed
   the label's removal, as for any protected object, and its namespace goes with it, keys and all.

The kind test checks this, see [Jobs](../reference/ci-checks.md#jobs): it deletes a cluster's `Kustomization`s and
expects everything they applied to go, except the cluster's `HelmRelease` and `OCIRepository`. It also drops the
organisation's namespace `Kustomization` from the management cluster's build, and expects it and the cluster's
`Kustomization`s to stay.

## What kubectl-gs writes

From kubectl-gs 8.0.0 on, `kubectl gs gitops` writes the protection this page describes, except the annotation on the
`Kustomization`s everything else hangs off, and older releases write some of it:

| Command | Writes |
| --- | --- |
| `kubectl gs gitops add base`, 8.0.0 and newer | the annotation and the label on the cluster's `HelmRelease` and `OCIRepository`, and `global.metadata.preventDeletion: true` in the values, so the chart labels the `Cluster`. `--prevent-deletion=false` turns all of it off |
| `kubectl gs gitops add base`, 7.0.0 to before 8.0.0 | the label and `preventDeletion`, but no annotation |
| `kubectl gs gitops add organization`, 8.0.0 and newer | the annotation and the label on the `Organization` |
| `kubectl gs gitops add management-cluster` and `add encryption`, 8.0.0 and newer | a `kustomization.yaml` that gives the key Secrets in `MC_NAME/secrets` and `namespace/secrets` the annotation and the label |
| `kubectl gs gitops add management-cluster` and `add workload-cluster`, 8.0.0 and newer | `Kustomization`s with `prune: true`. Older releases write `prune: false`, so Flux deletes nothing from them at all |
| `kubectl gs template cluster`, 7.0.0 and newer | the label on the `OCIRepository` and `HelmRelease`, and `--prevent-deletion` defaults to `true`. No annotation |
| `kubectl gs gitops add base` and `template cluster`, before 7.0.0 | no label on the `HelmRelease` or `OCIRepository`, and no annotation. `template cluster --prevent-deletion`, off by default, labels only the cluster's values. From 6.0.6 they leave install remediation off |
| `kubectl gs gitops add organization` before 8.0.0, `kubectl gs template organization` | neither the label nor the annotation |

With an older kubectl-gs, or with `kubectl gs template`, add what's missing by hand, as the
[CAPA base](/bases/clusters/capa/cluster.yaml) and the example `Organization` have it. Without the annotation, the
`prune: true` this repository uses makes Flux try to delete the cluster when its file goes. Whichever release you
use, add the annotation to `MC_NAME.yaml` and the organisation's `namespace.yaml` yourself, see
[Let kubectl-gs write the files](../how-to/kubectl-gs.md).

## `ResourceSet`s

A Flux Operator `ResourceSet` can render a cluster's `OCIRepository` and `HelmRelease` instead of a `Kustomization`, as
the scheduled-upgrades example does, see
[Hold upgrades for a window](../tutorials/advanced/scheduled-upgrades.md). It prunes too: when its input goes, it
deletes what it rendered for it. Its input is a version, which in Flux Operator v0.62.1 goes only when no tag matches
the range: a provider that can't read the registry keeps its last version, and a deleted provider stalls the
`ResourceSet` rather than emptying it. Two guards cover it all the same:

- The `ResourceSet` has its provider in `dependsOn`, with a `readyExpr` that needs exported inputs. Until the provider
  is `Ready` with a version, the `ResourceSet` reports `DependencyNotReady` and leaves what it rendered as it is.
- The cluster's `OCIRepository` and `HelmRelease` have the `fluxcd.controlplane.io/prune: disabled` annotation, Flux
  Operator's version of Flux's, so the `ResourceSet` never deletes them, not even when the `ResourceSet` itself is
  deleted or its file is deleted from Git. They keep the `giantswarm.io/prevent-deletion` label, as in the cluster
  base.

[Keep the version](../tutorials/advanced/scheduled-upgrades.md#keep-the-version) shows the guard, and the kind test
tries all three, an unreadable registry, a range no tag matches and a deleted provider, and checks that the cluster
stays.
