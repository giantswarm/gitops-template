# One owner per object

> [!Caution]
> Every object has exactly one thing that reconciles it. A reconciler can't tell whether it really owns an object: it
> knows only what it was told to apply. Give an object two of them, or the same one twice, and each keeps putting the
> object back the way it wants it, and nothing reports an error.

Picture two gardeners working one bed from two planting plans. Each plants what's on their plan, and pulls up what
isn't. Neither is wrong by their own plan, and the bed changes every time one of them walks past. That's what happens
when two reconcilers share an object, and it's easier to set up than it sounds: a file listed in two places, an app
installed twice by two tools, a Secret written from Git and from a secret manager. This page says why nothing stops
you, the forms it takes in this repository, how to find out who's writing an object, and how to stay out of it.

## Why nothing stops you

A reconciler knows its own desired state and little else. kustomize-controller knows what a `Kustomization` builds,
the inventory of what it applied last time, and the `kustomize.toolkit.fluxcd.io/name` and
`kustomize.toolkit.fluxcd.io/namespace` labels it writes on each object. helm-controller knows the `HelmRelease` and
the release history it recorded in the `HelmRelease`'s status. Neither asks the cluster whether something else claims
the object, and the cluster has no way to tell them.

Server-side apply, which kustomize-controller uses, would report a conflict when two field managers set the same field.
It doesn't get the chance:

- Every Flux `Kustomization` applies with the same field manager, `kustomize-controller`. To the API server, two
  `Kustomization`s writing one object are one owner changing its mind.
- kustomize-controller applies with `force`, so it takes over fields that another manager set, rather than stopping at
  the conflict. It also strips the fields `kubectl apply` left behind.
- `spec.force: true` on a `Kustomization` is something else: it deletes and recreates an object whose immutable fields
  changed. It doesn't decide between two writers.

Admission doesn't help either. A second writer sends an ordinary, valid request, and nothing in the API server asks
whether another tool writes the same object. The labels don't stop anything: each `Kustomization` writes its own name
into `kustomize.toolkit.fluxcd.io/name` when it applies, so the label shows whichever applied last.

Pruning is where it gets dangerous. When a `Kustomization` stops listing an object it applied, it deletes it only if
the object's labels still name that `Kustomization`. So if the other one applied it last, nothing happens. If this
one did, the object is deleted, and the other `Kustomization` creates it again at its next run, because it still
lists it. For a `HelmRelease`, that's an uninstall and an install. For a cluster's `HelmRelease`, it's the cluster,
which is one reason those carry the protection in [Deletion protection](./deletion-protection.md).

helm-controller has its own version of the problem. A Helm release is a set of Secrets in its storage namespace, and
helm-controller compares the latest of them with the release it recorded itself. When the latest isn't one it made,
it logs `release not managed by controller`, clears its history and upgrades the release to bring it back under its
management. It does exactly the same when it adopts a release it has never seen, so it can't tell adoption from a
fight.

These statements come from kustomize-controller v1.7.3, helm-controller v1.4.5 and the `fluxcd/pkg/ssa` library they
use. What External Secrets Operator, Kyverno, app-operator and Flux Operator do is described below by what you see,
not by their code.

## The forms it takes here

### The same controller twice

One object in the build of two Flux `Kustomization`s. In this layout it happens when:

- a file is listed in two `kustomization.yaml` files that two `Kustomization`s build;
- a base is included by two `Kustomization`s that apply into the same namespace, with a name that doesn't start with
  `${cluster_name}`. Every cluster of an organisation applies into `org-<name>`, so two clusters with the same base
  write the same object, unless its name has the cluster in it;
- a cluster's directory is applied by the cluster's own `Kustomization` and by another one, such as a
  `kustomization.yaml` in the cluster's directory that lists `cluster/` next to `apps/`;
- `out-of-band/` isn't left out of the cluster's `kustomization.yaml`, so the cluster's `Kustomization` applies it to
  the management cluster while the `-direct` one, or the workload cluster's Flux, applies it to the workload cluster.

You see the `kustomize.toolkit.fluxcd.io/name` label change between two names, and a value that changes back if the
two builds differ, for example in their `postBuild` variables. If they build it the same, you see nothing at all,
until one of them stops listing it. Fix it by listing the object in one build only.

### Two `HelmRelease`s for one release

Two `HelmRelease`s, or a `HelmRelease` and one a `ResourceSet` renders, with the same `releaseName`, the same
`targetNamespace` and storage namespace, in the same cluster. It happens when a
[multicluster app](../tutorials/advanced/multicluster-apps.md) renders an app for a cluster that has it in its own
`apps` already, or when you move an app to a template or a stack and the old `HelmRelease` stays for a while.

Each upgrades the release over the other's revision, so the release's revision climbs with no change in Git, and its
values change with every upgrade. Fix it by suspending one `HelmRelease`, removing it once it is suspended, then
checking that the other reports `Ready`.

### Flux and the App Platform

An `App` and a `HelmRelease` for the same release in the same cluster. app-operator and chart-operator install the
`App` with Helm, and helm-controller installs the `HelmRelease`, into the same release. Each upgrades over the other.
It happens during a move from `App`s to `HelmRelease`s, if the `App` isn't gone before the `HelmRelease` arrives.
Deleting an `App` uninstalls what it installed, so ask Giant Swarm how to take the `App` away and keep the release
before you add the `HelmRelease`.

### Flux and External Secrets Operator

A SOPS-encrypted Secret and an `ExternalSecret` that write the same Secret, same name and same namespace.
kustomize-controller applies the SOPS copy at every run of its `Kustomization`, and External Secrets Operator writes
its own at every `refreshInterval`. Whichever wrote last wins, so the Secret flaps, and with the
`reconcile.fluxcd.io/watch` label on it, the app is upgraded each time it changes. Remove the `ExternalSecret`, and
External Secrets Operator deletes the Secret it owns, which Flux writes again at its next run.

It happens when you add a secret for an app that already has one by the other route. One route delivers each Secret.
If the app needs a value that only the other tool has, put it in the same source, the secret manager or the encrypted
file, or in a second Secret with its own name and its own `valuesFrom` entry, which helm-controller merges after the
first, see [App values](../reference/values.md#app-values). [Secrets](./secrets.md) says which route suits which
secret.

### Flux and Kyverno

A Kyverno policy that generates objects with `synchronize: true` puts each one back when it changes, and makes it
again when it's deleted. If Flux applies an object of the same name, the two take turns. The
[secret-stores](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/secret-stores/) example generates a
`SecretStore` and an `ExternalSecret` for every workload cluster, named after it: don't put objects with those names
in Git. A generated object has the `generate.kyverno.io/policy-name` label.

### Flux and an operator, or a person

Something in the cluster that owns part of an object: an autoscaler that sets a `Deployment`'s replica count, or an
operator or a webhook that fills in a field. If Flux sets that field too, they take turns at it. Leave the field out
of what Flux applies, or, for an app with helm-controller's drift detection on, add an `ignore` rule, as
[Correct changes made by hand](../how-to/update-app.md#correct-changes-made-by-hand) shows.

A person with `kubectl` is the same case. kustomize-controller sets back every field its files set at its next run,
so a hand change to what a `Kustomization` applies lasts minutes. What a chart installs in the workload cluster stays
changed until the release is upgraded, unless the `HelmRelease` has drift detection on. Change it in Git.

## Who is writing an object

Start with [Find what applied an object](../how-to/troubleshooting.md#find-what-applied-an-object): `flux trace` names
the Flux object behind it from its labels. Then look at the object yourself:

- Its labels: `kustomize.toolkit.fluxcd.io/name` and `/namespace` for a `Kustomization`, `helm.toolkit.fluxcd.io/name`
  and `/namespace` for a `HelmRelease`, `resourceset.fluxcd.controlplane.io/name` for a `ResourceSet`,
  `generate.kyverno.io/policy-name` for a Kyverno policy. A Secret External Secrets Operator wrote has an owner
  reference to its `ExternalSecret`.
- Its field managers, which list everything that has written to it and when:

    ```sh
    kubectl get KIND NAME -n NS --show-managed-fields -o yaml
    ```

    `kustomize-controller` and `helm-controller` are Flux. Another manager with a recent time on the same fields is
    the other writer.

The symptoms that point here:

- a value that keeps changing back;
- a `kustomize.toolkit.fluxcd.io/name` label that changes between two `Kustomization` names;
- a release whose revision climbs with no change in Git;
- an object that's deleted while a file for it is still in Git, and comes back a few minutes later.

## How to stay out of it

Give each object one deliverer, and only one. Before you add something that may exist already, build both suspects
and look for it in each:

```sh
tools/fake-flux build KUSTOMIZATION_NAME:NAMESPACE -M | grep -n 'name: OBJECT_NAME'
```

CI looks for the first of those forms for you. `test_no_object_has_two_kustomizations`, in
`tests/ats/test_one_owner.py`, builds what every Flux `Kustomization` of each management cluster applies, as Flux
builds it, and fails when two of them apply the same object to the same cluster, naming the object and both
`Kustomization`s. It counts what a `ResourceSet` renders and what a workload cluster's own Flux applies from your
repository too, and needs no cluster, so you can run it before you push. It doesn't see what a chart installs, what
Kyverno generates or what anything outside Flux writes (see [Objects in two builds](../reference/ci-checks.md#objects-in-two-builds)
for the whole list), so the other forms are still yours to look for. `tools/fake-flux` stops with
`is applied by more than one Kustomization` when one Flux `Kustomization` is in two builds, and the tests in
`tests/ats` fail when one Secret comes from both an `ExternalSecret` and a SOPS file.

To hand an object from one reconciler to another, take it away from the first before the second starts, and keep what
it installed: [adopting is handing over](../how-to/adopt-app.md), not sharing.
