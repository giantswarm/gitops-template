# Migrate a fork from structure version 2

A fork of this template doesn't follow the template by itself. If yours has a `mapi` directory in each workload
cluster, and its clusters' Flux `Kustomization`s in the `default` namespace, it's at
[structure version](../reference/repo-structure.md#structure-version) 2, the layout the template had before this
release. This page migrates it to version 3, the layout the docs describe: no `mapi`, and each organisation's objects
in its own namespace, `org-<name>`.

Flux doesn't care which version your repository is at: a fork you leave alone keeps reconciling exactly as it does
today. kubectl-gs does care. From kubectl-gs X.Y.Z on, `kubectl gs gitops add workload-cluster` and
`kubectl gs gitops add encryption --workload-cluster` refuse an organisation whose workload clusters' Flux
`Kustomization`s haven't moved into its namespace. So the day you want to add a cluster with the CLI, you have to do
the move first.

Some of it is mandatory, some of it is optional, and a little of it is the most dangerous thing in these docs: moving
`Kustomization`s that own running clusters. Each section says what it changes on a running management cluster. The
sections that move objects Flux manages are worth reading twice before you push.

- [What's mandatory](#whats-mandatory)
- [What's optional, and why you might want it](#whats-optional-and-why-you-might-want-it)
- [The path from main](#the-path-from-main)
- [Check and upgrade the structure version](#check-and-upgrade-the-structure-version)
- [Move to the kubectl-gs names](#move-to-the-kubectl-gs-names)
- [Give every cluster its region](#give-every-cluster-its-region)
- [Move an organisation's namespace objects](#move-an-organisations-namespace-objects)
- [Move the workload cluster `Kustomization`s](#move-the-workload-cluster-kustomizations)
- [Split a cluster's `Kustomization`](#split-a-clusters-kustomization)
- [Turn on pruning for the clusters](#turn-on-pruning-for-the-clusters)
- [Install apps into their own namespace](#install-apps-into-their-own-namespace)
- [Replace App Sets and Cluster Templates](#replace-app-sets-and-cluster-templates)
- [Move Envoy Gateway to the bundle](#move-envoy-gateway-to-the-bundle)
- [Move charts to `gsoci.azurecr.io`](#move-charts-to-gsociazurecrio)

## What's mandatory

| Change | Why |
| --- | --- |
| [Every cluster sets its region](#give-every-cluster-its-region), as a kustomize Component | Without a region, `release-aws` takes the region of the management cluster, and the template's bases and CI expect one |
| [The structure version 3 files](#check-and-upgrade-the-structure-version): no `mapi`, and an organisation `namespace.yaml` | `kubectl gs gitops upgrade` writes them. Every `kubectl gs gitops` command from X.Y.Z on writes this layout |
| [The workload cluster `Kustomization`s in the organisation's namespace](#move-the-workload-cluster-kustomizations) | kubectl-gs X.Y.Z and newer refuse to add clusters or cluster keys to an organisation that hasn't moved them |

## What's optional, and why you might want it

| Change | Why you might want it |
| --- | --- |
| [The kubectl-gs file names](#move-to-the-kubectl-gs-names) | `kubectl gs gitops check --adopt` and `add automatic-update` only find apps under these names |
| [A cluster `Kustomization` and an apps `Kustomization`](#split-a-clusters-kustomization) | The apps wait for the cluster's control plane to be up, instead of failing until it is |
| [`prune: true` on the clusters' `Kustomization`s](#turn-on-pruning-for-the-clusters) | Deleting an app's files uninstalls it. With `prune: false`, as on `main`, it stays, unmanaged |
| [Apps in their own namespace](#install-apps-into-their-own-namespace) | Apps no longer create an `org-<name>` namespace in the workload cluster. It reinstalls them |
| [Stacks and cluster bases](#replace-app-sets-and-cluster-templates) instead of `bases/app_sets` and `bases/cluster_templates` | One indirection fewer, and the layout the tutorials teach |
| [Envoy Gateway from the `gateway-api-bundle`](#move-envoy-gateway-to-the-bundle) instead of three charts | The bundle is how Giant Swarm supports Envoy Gateway |
| [Charts from an `OCIRepository`](#move-charts-to-gsociazurecrio) instead of a `HelmRepository` or `GitRepository` | Giant Swarm publishes its charts to `gsoci.azurecr.io`, and its old app catalogs aren't guaranteed to get new versions |

Changes to examples you don't use, such as new apps under `bases/`, need nothing from you.

If your fork has `App` custom resources of its own, Giant Swarm is
[deprecating the App Platform](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/)
that runs them, and `kubectl gs gitops upgrade` fails on any `App` it finds. To move an app to a `HelmRelease` without
installing it again, see [Adopt a release managed by an `App`](./adopt-app.md#adopt-a-release-managed-by-an-app).

## The path from main

Do the mandatory steps in this order. Take the optional ones once step 5 is done, one at a time, each in its own pull
request:

1. Update kubectl-gs to X.Y.Z or newer, with `kubectl gs selfupdate`, and start from a clean clone, on a new branch.
1. [Move to the kubectl-gs names](#move-to-the-kubectl-gs-names). Optional, but it's mostly renames, and the next
   step finds more of your repository with them. On the cluster, only each cluster's values ConfigMap gets a new name.
1. [Give every cluster its region](#give-every-cluster-its-region).
1. [Check and upgrade the structure version](#check-and-upgrade-the-structure-version), which drops `mapi` and adds
   each organisation's `namespace.yaml`.
1. [Move the workload cluster `Kustomization`s](#move-the-workload-cluster-kustomizations), one organisation at a time,
   in three commits each.

Wait for Flux to apply each push, and for everything to be `Ready` at that commit, before you start the next. If
something isn't, [When something isn't Ready](./troubleshooting.md) helps you find out why.

## Check and upgrade the structure version

The repository's layout has a version, the [structure version](../reference/repo-structure.md#structure-version),
which `kubectl gs gitops` records in `.gitops-metadata.yaml`. `check` and `upgrade` know version 3 from kubectl-gs
X.Y.Z on (see [kubectl-gs version](../reference/tools.md#kubectl-gs-version)). If yours is older, update it with
`kubectl gs selfupdate`.

To see which parts of your repository are behind, run this in your clone:

```sh
kubectl gs gitops check
```

It exits with an error when anything is behind, so you can run it in CI. If your repository is older than the
metadata file, run `kubectl gs gitops check --adopt` once to record what's there. It records it at version 2, the
layout of `main`, so it can't find drift from before you ran it. To see what it would record first:

```sh
kubectl gs gitops check --adopt --dry-run
```

Every app directory under `apps` is listed as an `app` layer. If the output lists directories under `Skipped`, they
still lack a `helm-release.yaml` or a `kustomization.yaml`. Rename them first, as
[Move to the kubectl-gs names](#move-to-the-kubectl-gs-names) describes, then record them in `.gitops-metadata.yaml`:

```sh
kubectl gs gitops check --adopt
```

To bring the repository up to date, first see what would change, and the steps it leaves to you:

```sh
kubectl gs gitops upgrade --dry-run
```

Then run the upgrade, and review the result with `git diff` before you commit it:

```sh
kubectl gs gitops upgrade
```

It changes the files in place and keeps your own edits where it can. It doesn't run on a repository with uncommitted
changes unless you pass `--force`, so you can always undo it with Git. It never changes a file Git ignores, such as a
decrypted secret, because Git can't give it back: it leaves the file where it is for you to move, and where one would
have to change, it refuses and says what to edit by hand.

It refuses, and writes nothing, when:

- It can't tell what a directory holds, for example when both `mapi/apps` and `apps` exist, or when a
  `kustomization.yaml` lists `out-of-band`.
- A cluster's directory already has a kustomization file (`kustomization.yaml`, `kustomization.yml` or
  `Kustomization`) next to `mapi`, and `mapi` has files to move up. That file doesn't list them, so the cluster's
  `Kustomization` would stop applying them, and delete them if it prunes. Move what `mapi` holds up and list it there
  by hand, or remove the file, then run the upgrade again.
- A Flux `Kustomization` applies `mapi`, or a directory in it, with `prune: true`, and builds an object from there
  without the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. The caution below says what to do.
- A rule in `.sops.yaml` picks the key for a file under `mapi`, or for a new `*.enc.yaml` next to it, and a different
  rule would pick it once the file has moved up. The paragraph on `.sops.yaml` below says what to change.

From version 2 to 3, it changes only files:

- Each workload cluster's `mapi` directory goes: `cluster`, `apps` and any other directories in it move up into the
  cluster's directory, next to `out-of-band`, with the relative paths in them corrected. The cluster's `Kustomization`
  points at the cluster's directory, whose new `kustomization.yaml` lists what it applies, never `out-of-band`.
- Each organisation gets a `Kustomization` of its own, `namespace.yaml`, with an empty `namespace` directory for it to
  apply. It also gets a `kustomization.yaml` that lists the `Organization` and `workload-clusters`.
- `MC_NAME/secrets` gets a `kustomization.yaml` that protects the SOPS keys in it, if it has none.

On the management cluster, the cluster's `Kustomization` applies the same objects from their new paths, and
`namespace.yaml` starts with nothing to apply. A fork of `main` has `prune: false` on every `Kustomization`, so nothing
is deleted on the way.

> [!Caution]
> If you've already given your clusters' `Kustomization`s `prune: true`, objects that change path can be deleted and
> created again while they move, so the upgrade refuses until they're protected. First annotate every object under
> `mapi` with `kustomize.toolkit.fluxcd.io/prune: disabled` (`OCIRepository`s, ConfigMaps and Secrets as well as
> `HelmRelease`s), push, and wait for Flux to apply it. The easy way is `commonAnnotations` in each
> `kustomization.yaml` under `mapi`, which annotates everything it builds, generated ConfigMaps and Secrets included:
>
> ```yaml
> commonAnnotations:
>   kustomize.toolkit.fluxcd.io/prune: disabled
> ```
>
> The annotation on each object a `kustomization.yaml` lists counts too, but not when it generates objects or lists a
> remote resource: that one needs `commonAnnotations`.
> Run the upgrade in the next commit, and remove the annotations once the `Kustomization`s are `Ready` at that commit.
> Keep it on the objects that carry it anyway, such as the cluster's `HelmRelease`.

The per-cluster rules in `.sops.yaml` are yours to change, before you run the upgrade: it never changes `.sops.yaml`.
A fork of `main` has rules whose `path_regex` names a cluster's `mapi/` directory, which the upgrade removes. A new
`*.enc.yaml` in the cluster's `cluster` or `apps` would then match no rule, and `sops` refuses it; or it matches a
broader rule further down and is encrypted with the wrong key. So the upgrade refuses while such a rule is there. In
each one, replace `mapi/` with `(mapi/)?(cluster|apps)/`, or with `(mapi/)?(cluster|apps|app_sets)/` for a cluster
that still has App Sets. That matches both layouts, and keeps the rule out of `out-of-band`, where the cluster's key
can't decrypt. Once the upgrade has run, drop `(mapi/)?`. Files already encrypted keep their keys: the rules only
decide what a file gets the next time `sops` encrypts it. Then check that every encrypted file, and a new one in each
cluster's `apps`, meets the rule you mean, which is the first one that matches its path:

```sh
check_rules() {
  for f in "$@"; do
    rule=$(yq '.creation_rules[].path_regex' .sops.yaml | while read -r r; do
      if printf '%s\n' "${f}" | grep -Eq -- "${r}"; then printf '%s\n' "${r}"; break; fi
    done)
    printf '%s\t%s\n' "${f}" "${rule:-NO RULE}"
  done
}
check_rules $(git ls-files '*.enc.yaml')
check_rules management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/apps/new.enc.yaml
```

The upgrade prints what it leaves to you. The workload clusters' `Kustomization`s stay in `default`, applied by
`MC_NAME.yaml`, with their keys in `MC_NAME/secrets`: move them as
[Move the workload cluster `Kustomization`s](#move-the-workload-cluster-kustomizations) describes. It doesn't split a
cluster's `Kustomization`, change `prune`, move apps to their own namespace or replace App Sets and Cluster
Templates; the optional sections below do.

Layers recorded without a structure version can't be upgraded. If you know the version they were created with, set
their `structureVersion` by hand. Otherwise, remove their entries and run `kubectl gs gitops check --adopt`.

## Move to the kubectl-gs names

This template uses the file and resource names that `kubectl gs gitops` generates. Earlier versions of the template,
`main` among them, used names of their own, so `kubectl gs gitops check --adopt` skips their apps, and
`kubectl gs gitops add automatic-update` and the `gitops upgrade` migrations can't find their files. The move is all
renames, and only one of them shows on the clusters: each cluster's values ConfigMap gets its new name, and the old one
stays behind (see [Rename the cluster user config](#rename-the-cluster-user-config)). The merged values, and so the
clusters, don't change.

### What changed

| What | Old name | New name |
| --- | --- | --- |
| An app's `HelmRelease` | `helmrelease.yaml` | `helm-release.yaml` |
| An app's `OCIRepository` | `ocirepository.yaml` | `oci-repository.yaml` |
| A cluster's values ConfigMap | `cluster_user_config.yaml` | `cluster_userconfig.yaml` |
| The patch that adds it to the cluster's `HelmRelease` | `patch_user_config.yaml` | `patch_cluster_userconfig.yaml` |
| The ConfigMap's name | `${cluster_name}-user-config` | `${cluster_name}-cluster-userconfig` |
| A workload cluster's Flux `Kustomization` | `clusters-WC_NAME` | `MC_NAME-clusters-WC_NAME` |
| The CAPA cluster base | `helmrelease.yaml`, `ocirepository.yaml` | `cluster.yaml` |
| The envoy-gateway stack | `helmreleases.yaml`, `ocirepositories.yaml` | a directory for its one chart, the bundle |

`kubectl gs gitops` relies on the app and cluster user config names. It doesn't read the `Kustomization` names or
the files of the cluster base, so renaming those is optional and only makes your repository look like what
`kubectl gs gitops add` creates.

### Before you start

Start from a clean clone of your repository, on a new branch:

```sh
git switch -c kubectl-gs-names
```

Every command below runs from the root of the clone.

### Rename the app files

1. Rename the files everywhere in the repository: the apps of the workload clusters, the App Templates under
   `bases/apps`, and the cluster bases under `bases/clusters`, which you can merge into one file later (see
   [Align the CAPA cluster base](#align-the-capa-cluster-base-optional)):

    ```sh
    for f in $(git ls-files '*/helmrelease.yaml'); do
      git mv "$f" "$(dirname "$f")/helm-release.yaml"
    done
    for f in $(git ls-files '*/ocirepository.yaml'); do
      git mv "$f" "$(dirname "$f")/oci-repository.yaml"
    done
    ```

1. Change the references in the `kustomization.yaml` files:

    ```sh
    git ls-files '*kustomization.yaml' | xargs sed -i \
      -e 's/helmrelease\.yaml/helm-release.yaml/g' \
      -e 's/ocirepository\.yaml/oci-repository.yaml/g'
    ```

    On macOS, use `sed -i ''`.

1. If a base keeps several `HelmRelease`s or `OCIRepository`s in one file, like the envoy-gateway stack did, split
   it into a directory per chart, each with a `helm-release.yaml` and an `oci-repository.yaml`, as
   [bases/stacks/envoy-gateway](/bases/stacks/envoy-gateway/kustomization.yaml) has for its bundle.

Nothing changes in the clusters: Flux applies the same resources from the new files.

### Rename the cluster user config

1. Rename the files of every workload cluster, and of the environments that have them:

    ```sh
    for f in $(git ls-files '*cluster_user_config.yaml'); do
      git mv "$f" "$(dirname "$f")/cluster_userconfig.yaml"
    done
    for f in $(git ls-files '*patch_user_config.yaml'); do
      git mv "$f" "$(dirname "$f")/patch_cluster_userconfig.yaml"
    done
    ```

1. Rename the ConfigMap, in the ConfigMaps, in the patches, and in the `configMapGenerator`s with
   `behavior: replace` that replace it:

    ```sh
    git ls-files '*.yaml' ':!:*.enc.yaml' | xargs sed -i \
      -e 's/cluster_user_config\.yaml/cluster_userconfig.yaml/g' \
      -e 's/patch_user_config\.yaml/patch_cluster_userconfig.yaml/g' \
      -e 's/\${cluster_name}-user-config/${cluster_name}-cluster-userconfig/g'
    ```

    Encrypted files are left out, because changing them breaks their SOPS checksum. If one of them names the
    ConfigMap, decrypt it, change it and encrypt it again.

1. Check that nothing still uses the old names:

    ```sh
    git grep -n -e user_config -e '-user-config'
    ```

    Rename what it finds by hand, for example the `WC_NAME-user-config` ConfigMaps in `tests/ats/assertions` if your
    repository runs the [kind test](../reference/ci-checks.md#the-kind-test).

Flux creates the new ConfigMap and points the cluster's `HelmRelease` at it. The merged values stay the same. If the
workload cluster `Kustomization`s have `prune: true`, as in this template, Flux deletes the old `-user-config` ConfigMap
too. If they have `prune: false`, as in earlier versions, it stays on the management cluster. Delete it once the
cluster's `HelmRelease` is `Ready` again:

```sh
kubectl delete configmap WC_NAME-user-config -n org-ORG_NAME
```

### Rename the workload cluster `Kustomization`s (optional)

Renaming a Flux `Kustomization` creates a new one. If the `Kustomization` that applies it has `prune: true`, as in this
template, Flux deletes the old one. If it has `prune: false`, as in earlier versions, the old one stays, and both apply
the same resources until you delete it. A fork of `main` still has its workload cluster `Kustomization`s in
`default`, which the management cluster's `Kustomization` applies, so the commands below use `-n default`. Rename them
before you [move the workload cluster Kustomizations](#move-the-workload-cluster-kustomizations), or not at all: the
move gives them new objects anyway.

> [!Caution]
> Check that the old workload cluster `Kustomization` has `prune: false` before you go on. Deleting a
> `Kustomization` with `prune: true` deletes what it applied, such as the cluster's apps, before the new one takes it
> over. The cluster's `HelmRelease` stays only if it has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation
> or the `giantswarm.io/prevent-deletion` label (see
> [The protected objects](../explanation/deletion-protection.md#the-protected-objects)).

1. Check the `prune` setting of the old `Kustomization`:

    ```sh
    kubectl get kustomization clusters-WC_NAME -n default -o jsonpath='{.spec.prune}'
    ```

    If it prints `true`, set `prune: false` in its file first, push, and wait until Flux has applied it.

1. Change `metadata.name` in
   `management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml` to
   `MC_NAME-clusters-WC_NAME`, and the same for `WC_NAME-direct.yaml` next to it if you have one. If your repository
   runs the [kind test](../reference/ci-checks.md#the-kind-test), rename the `Kustomization` in the
   `gitops_ignored_objects` input of `.github/workflows/validate.yaml` and in the `kustomize.toolkit.fluxcd.io/name`
   labels of `tests/ats/assertions` too.

1. After you merge, Flux creates the new `Kustomization`. If the `Kustomization` that applies it has `prune: false`,
   delete the old one by hand:

    ```sh
    kubectl delete kustomization clusters-WC_NAME -n default
    ```

1. If you set `prune: false` in the first step, set `prune: true` again in the renamed file, and push.

### Align the CAPA cluster base (optional)

If your repository has its own copy of the CAPA cluster base, compare it with the
[one in this template](/bases/clusters/capa). It now has one `cluster.yaml` with the `OCIRepository` and the
`HelmRelease`, as `kubectl gs gitops add base --provider capa` writes. Merge your two files into it and change
`kustomization.yaml` to list `cluster.yaml`. The base's [readme](/bases/clusters/capa/readme.md) lists where
it differs from the CLI's on purpose.

### Record the layers

Once the files are renamed, `kubectl gs gitops` recognises the apps. Commit and push, then record them as
[Check and upgrade the structure version](#check-and-upgrade-the-structure-version) describes:

```sh
git add -A && git commit -m "Use the kubectl-gs file and resource names" && git push
```

## Give every cluster its region

On `main`, a region is optional, and a cluster lists one as a kustomize base under `resources:`. Here, every cluster
sets one, as a kustomize Component that appends `${cluster_name}-region-config` to the cluster's `valuesFrom` (see
[Stages and regions](../tutorials/intermediate/stages-and-regions.md#regions)). A cluster without a region gets the
region of the management cluster's nodes from `release-aws`, which is rarely what anyone meant.

A running cluster has to keep the region it runs in. A region Component that names another one tries to build the
cluster somewhere else, so set each cluster's region to where it is now.

1. Find the region each cluster runs in. This is for clusters on AWS; on another provider, see
   [Regions](./other-providers.md#regions) for what a cluster needs in its place:

    ```sh
    kubectl get awsclusters -n org-ORG_NAME -o custom-columns=NAME:.metadata.name,REGION:.spec.region
    ```

1. Copy the template's regions, in [bases/environments/regions](/bases/environments/regions/), into your fork, or turn
   yours into Components the same way: `kind: Component`, `apiVersion: kustomize.config.k8s.io/v1alpha1`, and a patch
   that appends the region's ConfigMap to `/spec/valuesFrom/-`. A region sets only `global.providerSpecific.region`.
   On `main`, a region's file also defined a node pool, `xxxxx` in the example, in the region's zones. The template's
   region doesn't, so a cluster that took a pool from its region loses it when you switch, and a pool that disappears
   from the values is a node pool Cluster API deletes. Carry the pool over before you switch, under the same name and
   with the same values: either in a Component of its own, as the template's `regions/*/node_pool` Components add the
   `large` pool, or in the cluster's own values.
1. In each cluster's `cluster/kustomization.yaml`, take the region out of `resources:` and list it under
   `components:` instead, and give every cluster that has none the region from the first step. Drop any patch that
   inserts the region's ConfigMap at a fixed position, such as `/spec/valuesFrom/1`.
1. Check the order of the layers before you push. The region has to come after the base's `${cluster_name}-config`
   and before the cluster's own values, and the values in it have to be the ones the cluster has now:

    ```sh
    tools/fake-flux build CLUSTER_KUSTOMIZATION '. | select(.kind == "HelmRelease" and .metadata.name == "CLUSTER_NAME") | .spec.valuesFrom'
    ```

When the merged values don't change, Flux doesn't upgrade the cluster's release. A cluster made from a Cluster
Template gets its region the same way, in the cluster's own `kustomization.yaml`, and
[Replace App Sets and Cluster Templates](#replace-app-sets-and-cluster-templates) says how to drop the template later.

## Move an organisation's namespace objects

You need this section only if `MC_NAME.yaml` applies objects of your own in an organisation's namespace, such as
`ExternalSecret`s you listed in the organisation's directory, and you want the organisation's `namespace.yaml` to apply
them instead, as the template does. The workload clusters' `Kustomization`s have
[a section of their own](#move-the-workload-cluster-kustomizations).

On a management cluster that already runs the repository, moving objects from what `MC_NAME.yaml` applies into the
organisation's `namespace` directory deletes them once. Flux deletes what leaves a `Kustomization`'s inventory in the
same reconciliation. `MC_NAME.yaml` always applies a commit first, because the organisation's namespace
`Kustomization` names it in `dependsOn`, so the objects are gone before that `Kustomization` creates them again. Some
of those deletions reach further: deleting the `-direct` `Kustomization` deletes what it applied in the workload
cluster, and deleting an `ExternalSecret` deletes the Secret it wrote.

To move them without a deletion, use three commits, and let Flux apply each one before you push the next:

1. Annotate every object that moves with `kustomize.toolkit.fluxcd.io/prune: disabled`. `MC_NAME.yaml` applies the
   annotation, so Flux leaves the objects when they leave its inventory.
1. Move the objects into `namespace`, list them in `namespace/kustomization.yaml`, and take them out of the
   organisation's `kustomization.yaml`, as in
   [Add an organisation](../tutorials/basic/getting-started.md#2-add-an-organisation). `MC_NAME.yaml` applies the
   commit first: it leaves the annotated objects where they are, and `namespace.yaml` then takes them over.
1. Remove the annotation, so Flux deletes the objects again when you delete them from Git. Leave it on SOPS key
   Secrets: like the ones in `MC_NAME/secrets`, they keep `kustomize.toolkit.fluxcd.io/prune: disabled` for good.

A new management cluster needs none of this: its organisations' namespaces don't exist yet.

## Move the workload cluster `Kustomization`s

On `main`, the workload clusters' `Kustomization`s are in `default`: `MC_NAME.yaml` applies the organisation's
`workload-clusters` directory, and the cluster keys are in `MC_NAME/secrets`. A `-direct` one is in the organisation's
namespace already, applied by `MC_NAME.yaml` from the same directory. Here, their files stay in `workload-clusters`,
but the organisation's `namespace.yaml` applies them, into the organisation's namespace, as its `automation`
ServiceAccount, with their keys in `namespace/secrets`. kubectl-gs X.Y.Z and newer won't add a cluster to an
organisation until they've moved. On a management cluster that already runs them, move them in three commits, and let
Flux apply each one before you push the next.

> [!Caution]
> This procedure has been reasoned through against Flux's source, and its steps checked for files, but it has not
> been rehearsed on a live management cluster. Try it first on an organisation whose clusters you can afford to lose,
> or on a test installation, and keep the warning below in mind.

Before you start:

- The organisation's `namespace.yaml` runs and is `Ready`. `kubectl gs gitops upgrade` writes it (see
  [Check and upgrade the structure version](#check-and-upgrade-the-structure-version)).
- `MC_NAME.yaml` needs `prune: true` by the second commit, so that Flux deletes the old `Kustomization`s in
  `default`. With `prune: false`, as in `main` and in what kubectl-gs before X.Y.Z writes, they stay, and the old and
  the new `Kustomization`s both reconcile the same clusters. The first commit sets it.
- kustomize-controller supports `spec.deletionPolicy`: `kubectl explain kustomization.spec.deletionPolicy` describes
  it. The Flux of Giant Swarm management clusters does.
- Move each cluster's `Kustomization`s together: the apps `Kustomization` names its cluster's in `dependsOn`, in its
  own namespace.

> [!Caution]
> Don't move the `Kustomization`s without the first commit. Flux deletes the old ones in `default` when
> their files leave `MC_NAME.yaml`'s build, and their finalizer deletes what they applied before the new ones in the
> organisation's namespace exist. Every app on the workload clusters would be uninstalled, and the clusters' values,
> `ExternalSecret`s and the Secrets they wrote, `PushSecret`s and application teams' `Kustomization`s would go. Only
> the clusters' `HelmRelease`s and `OCIRepository`s would stay. A `-direct` `Kustomization` that `MC_NAME.yaml`
> applies goes the same way, and deletes what it applied in the workload cluster. `deletionPolicy: Orphan` makes the
> finalizer delete nothing, and `kustomize.toolkit.fluxcd.io/prune: disabled` keeps Flux from deleting the
> `Kustomization` at all.

Export the names the commands below use:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export ORG_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}
```

1. The first commit moves nothing:

    - Protect what `MC_NAME.yaml` applies and has to keep, whatever its `prune` is now, as
      [The protected objects](../explanation/deletion-protection.md#the-protected-objects) lists: the SOPS key Secrets
      in `MC_NAME/secrets`, which the second commit takes out of its build, and the `Organization`s. Give them the
      `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the `giantswarm.io/prevent-deletion` label, and
      give `MC_NAME.yaml` `prune: true`. This commit takes nothing out of its build, so turning `prune` on deletes
      nothing: Flux deletes only what leaves the build once it's on. The commands leave alone what's there already,
      and stop at the first one that fails:

      ```sh
      (
        set -eu
        yq -i '.commonAnnotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
          with(select([.labels[]?.pairs["giantswarm.io/prevent-deletion"]] | all_c(. != "true"));
            .labels += [{"pairs": {"giantswarm.io/prevent-deletion": "true"}}])' \
          management-clusters/${MC_NAME}/secrets/kustomization.yaml
        organizations=$(yq -N 'select(.kind == "Organization") | filename' \
          management-clusters/${MC_NAME}/organizations/*/*.yaml | sort -u)
        : "${organizations:?no Organization found}"
        for f in $(echo "${organizations}"); do
          yq -i 'with(select(.kind == "Organization");
            .metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
            .metadata.labels["giantswarm.io/prevent-deletion"] = "true")' ${f}
        done
        yq -i '.spec.prune = true' management-clusters/${MC_NAME}/${MC_NAME}.yaml
      )
      ```

    - Protect every `Kustomization` in the organisation's `workload-clusters`, according to the namespace it's in.
      One in `default` moves to the organisation's namespace, so Flux deletes it and creates a new one: add
      `deletionPolicy: Orphan`. One already in the organisation's namespace (a `-direct` one) keeps its name and
      namespace, so `namespace.yaml` takes the same object over: add the `kustomize.toolkit.fluxcd.io/prune: disabled`
      annotation, so that `MC_NAME.yaml` leaves it when its file leaves the build. `deletionPolicy: Orphan` would keep
      what it applied, but Flux would still delete the `Kustomization` while `namespace.yaml` applies it again:

      ```sh
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        [ "$(basename ${f})" = kustomization.yaml ] && continue
        case "$(yq '.metadata.namespace' ${f})" in
          default | null) yq -i '.spec.deletionPolicy = "Orphan"' ${f} ;;
          *) yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled"' ${f} ;;
        esac
      done
      ```

    - Add the rule for the workload clusters' keys in `namespace/secrets` to `.sops.yaml`, ahead of the other rules,
      so an organisation key's rule for `namespace/secrets` can't take them (see
      [SOPS keys](../reference/sops-keys.md#encryption-rules)):

      ```sh
      export MASTER_KEY_FP=$(gpg --show-keys --with-colons management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc |
        awk -F: '/^fpr/{print $10; exit}')
      yq -i '.creation_rules = [{
        "encrypted_regex": "^(data|stringData)$",
        "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/[^/]+/namespace/secrets/.*\\.(gpg|age)key\\.enc\\.yaml",
        "pgp": "'"${MASTER_KEY_FP}"'"
      }] + .creation_rules' .sops.yaml
      ```

    - Copy each key Secret in `default` that those `Kustomization`s name in `decryption.secretRef` into the
      organisation's `namespace/secrets`, in the organisation's namespace, and list it in
      `namespace/secrets/kustomization.yaml`. If the organisation doesn't have that directory yet, create it with its
      `kustomization.yaml` as in [Add a workload cluster key (GPG)](./sops.md#add-a-workload-cluster-key-gpg), and
      list `secrets` in `namespace/kustomization.yaml`. With the master private key in your keyring, decrypt each key
      file, such as `WC_NAME.gpgkey.enc.yaml`, change its namespace and encrypt it again on its way into the new file.
      That way the private key never sits in the repository in plain text. This needs `sops` 3.10.0 or newer (see
      [Tools](../reference/tools.md#tools)). If `sops` finds no rule for the new path, it fails and leaves the file
      empty:

      ```sh
      export KEY_FILE=WC_NAME.gpgkey.enc.yaml
      sops --decrypt management-clusters/${MC_NAME}/secrets/${KEY_FILE} |
        yq '.metadata.namespace = "org-'"${ORG_NAME}"'"' |
        sops --encrypt --filename-override ${ORG_DIR}/namespace/secrets/${KEY_FILE} /dev/stdin \
        > ${ORG_DIR}/namespace/secrets/${KEY_FILE}
      yq -i '.resources += [strenv(KEY_FILE)]' ${ORG_DIR}/namespace/secrets/kustomization.yaml
      ```

   Commit with this message, because the third commit uses it to find this one. If you merge it through a pull
   request, keep the message as the commit's subject, for example as the title of a squash merge:

    ```sh
    git commit -m "protect the workload cluster Kustomizations of ${ORG_NAME} before the move"
    ```

   Push, and wait until `MC_NAME-gitops` and `MC_NAME-organization-ORG_NAME` are `Ready` at this revision. Check
   that `MC_NAME-gitops` prints `true`, that every old `Kustomization` in `default` prints `Orphan`, that every
   `-direct` one prints `disabled`, that the keys in `default` print `disabled`, and that the keys are in the
   organisation's namespace:

    ```sh
    kubectl get kustomization -n default \
      -o custom-columns=NAME:.metadata.name,PRUNE:.spec.prune,DELETION:.spec.deletionPolicy
    kubectl get secret -n default -l giantswarm.io/prevent-deletion=true \
      -o custom-columns='NAME:.metadata.name,PRUNE:.metadata.annotations.kustomize\.toolkit\.fluxcd\.io/prune'
    kubectl get kustomization -n org-${ORG_NAME} \
      -o custom-columns='NAME:.metadata.name,PRUNE:.metadata.annotations.kustomize\.toolkit\.fluxcd\.io/prune'
    kubectl get secret -n org-${ORG_NAME} -l giantswarm.io/prevent-deletion=true
    ```

1. The second commit moves the `Kustomization`s:

    - Take `workload-clusters` out of the organisation's `kustomization.yaml`, and list `../workload-clusters` in
      `namespace/kustomization.yaml` instead. kubectl-gs looks for exactly that entry to tell that the organisation has
      moved. `workload-clusters/kustomization.yaml` keeps listing the `Kustomization` files.
    - Change each file as [Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations) describes: no
      `metadata.namespace`, `sourceRef.namespace`, `organization: "${organization}"`, `org-${organization}` as the
      namespace of a `Cluster` health check, the organisation's namespace `Kustomization` in `dependsOn` where there's
      no `dependsOn` yet, and no `deletionPolicy`.
      `sourceRef.namespace` keeps the namespace of the `GitRepository` each one reads now: one without it reads the one
      in its own namespace. The `-direct` ones keep the annotation until the third commit:

      ```sh
      export ORG_KUSTOMIZATION=$(yq '.metadata.name' ${ORG_DIR}/namespace.yaml)
      yq -i '.resources |= ((. // []) + ["../workload-clusters"] | unique)' ${ORG_DIR}/namespace/kustomization.yaml
      yq -i 'del(.resources[] | select(. == "workload-clusters"))' ${ORG_DIR}/kustomization.yaml
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        [ "$(basename ${f})" = kustomization.yaml ] && continue
        yq -i '.spec.sourceRef.namespace = (.spec.sourceRef.namespace // .metadata.namespace // "default") |
          del(.metadata.namespace, .spec.deletionPolicy) |
          .spec.postBuild.substitute.organization = "${organization}" |
          with(.spec | select(has("healthChecks")) | .healthChecks[] | select(.kind == "Cluster");
            .namespace = "org-${organization}") |
          with(.spec | select(has("dependsOn") | not);
            .dependsOn = [{"name": strenv(ORG_KUSTOMIZATION), "namespace": "default"}])' ${f}
      done
      ```

      The template's `Kustomization`s read the repository's `GitRepository` in `default`. If one now names another
      namespace, such as a `-direct` one, which on `main` names none, check that it reads this repository:
      `kubectl get gitrepository -n org-${ORG_NAME}`. If it does, set its `sourceRef.namespace` to `default`, as the
      template does. Otherwise keep it.

    - List the `Kustomization`s by name in the organisation's commit-status `Alert`, if it has one, as the template
      does. The management cluster's `Alert` sees only `default` (see [Commit statuses](./commit-statuses.md)):

      ```sh
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        [ "$(basename ${f})" = kustomization.yaml ] && continue
        NAME="$(yq '.metadata.name' ${f})" yq -i '.spec.eventSources = ((.spec.eventSources // []) +
          [{"kind": "Kustomization", "name": strenv(NAME)}] | unique_by(.name))' \
          ${ORG_DIR}/namespace/notifications/commit-status-alert.yaml
      done
      ```

    - Take the keys you copied out of `MC_NAME/secrets/kustomization.yaml`, and `git rm` their files there. Keep a
      key that another organisation's `Kustomization`s in `default` still name: `MC_NAME/secrets` serves the whole
      management cluster.

   Push. `MC_NAME.yaml` deletes the old `Kustomization`s in `default`, which leave what they applied. It leaves the
   `-direct` ones, which have the annotation, and the old keys in `default`, which have
   `kustomize.toolkit.fluxcd.io/prune: disabled`. `namespace.yaml` then creates the new `Kustomization`s. They decrypt
   with the keys the first commit put in the organisation's namespace, and take over the objects without changing them:
   the `HelmRelease`s don't upgrade, and nothing is uninstalled. `namespace.yaml` takes the `-direct` ones over as
   they are. Check that the new ones are `Ready`, that `namespace.yaml` owns them, that none of the old ones is left,
   and that the objects name their new owner's namespace:

    ```sh
    flux get kustomizations -n org-${ORG_NAME}
    kubectl get kustomization -n org-${ORG_NAME} -L kustomize.toolkit.fluxcd.io/name
    kubectl get kustomization -n default
    kubectl get helmrelease -n org-${ORG_NAME} -L kustomize.toolkit.fluxcd.io/namespace
    ```

   If an old one is still in `default`, `MC_NAME.yaml` left it because it has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, perhaps one you gave it yourself. Delete it by hand. It
   has `deletionPolicy: Orphan`, so its finalizer deletes nothing it applied:

    ```sh
    kubectl delete kustomization -n default KUSTOMIZATION_NAME
    ```

1. The third commit removes the annotation from the `-direct` `Kustomization`s once `namespace.yaml` owns them, so
   that Flux deletes them again when you delete their files from Git. It removes it only from the files the first
   commit gave it to. The commands find that commit by its message and compare each file there with the same file in
   its parent, so a file that had the annotation before keeps it. They stop if they can't find the first commit:

    ```sh
    (
      set -eu
      first=$(git log --format=%H -1 --fixed-strings \
        --grep "protect the workload cluster Kustomizations of ${ORG_NAME} before the move")
      : "${first:?no first commit in the history of HEAD}"
      annotation='.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"]'
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        [ "$(basename ${f})" = kustomization.yaml ] && continue
        git cat-file -e ${first}:${f} 2>/dev/null || continue
        added=$(git show ${first}:${f} | yq "${annotation}")
        had=$(git show ${first}^:${f} | yq "${annotation}")
        if [ "${added}" = disabled ] && [ "${had}" != disabled ]; then
          yq -i "del(${annotation}) | del(.metadata.annotations | select(length == 0))" ${f}
        fi
      done
    )
    ```

1. Once no `Kustomization` in `default`, of any organisation, names them, delete the old keys from `default` by hand.
   For each one, check that this prints nothing, then remove its label and delete it:

    ```sh
    kubectl get kustomization -n default --no-headers \
      -o custom-columns=NAME:.metadata.name,KEY:.spec.decryption.secretRef.name | awk '$2 == "KEY_SECRET"'
    kubectl label secret -n default KEY_SECRET giantswarm.io/prevent-deletion-
    kubectl delete secret -n default KEY_SECRET
    ```

The cluster directories don't move, so the `path`s and the per-cluster rules in `.sops.yaml` stay as they are. The new
`Kustomization`s run as the organisation's `automation` ServiceAccount, which may write only in the organisation's
namespace. A cluster directory that applies anything else fails with "forbidden" (see
[Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations)).

## Split a cluster's `Kustomization`

On `main`, one `Kustomization` per cluster applies the cluster and its apps together, so the apps fail and retry until
the cluster is up. Here, a cluster with apps has two. `WC_NAME.yaml` applies `cluster` (the cluster's `HelmRelease`
and its base apps) and waits for the Cluster API `Cluster`'s control plane to be up. `WC_NAME-apps.yaml` applies the
rest once it is (see [Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations)). The `HELLO_APP_*`
examples have no secondary apps and keep one.

Do this after [Move the workload cluster `Kustomization`s](#move-the-workload-cluster-kustomizations), and while the
cluster's `Kustomization` still has `prune: false`: objects then change owner without being deleted on the way.

1. Move the base apps, the ones the cluster needs from the start, into `cluster/apps`, and list them in
   `cluster/kustomization.yaml`. Make sure `${WC_NAME}/kustomization.yaml` lists `apps/` and anything else the apps
   `Kustomization` should apply, but not `cluster/` or `out-of-band/`. A directory it doesn't list stops being
   applied.
1. Add the apps `Kustomization`, `WC_NAME-apps.yaml`, with the cluster's `Kustomization` in `dependsOn`, and the same
   `postBuild` substitutions, `decryption`, `serviceAccountName` and `sourceRef`. List it in
   `workload-clusters/kustomization.yaml`, and in the organisation's commit-status `Alert` if it has one.
1. In the same commit, narrow the cluster's `Kustomization` to `path: ./.../WC_NAME/cluster`, and give it the health
   check and the `timeout` of the [WC_NAME.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml)
   example.

Push. The cluster's `Kustomization` stops applying the apps, and leaves them where they are, as its `prune` is off.
The apps `Kustomization` takes them over once the cluster's control plane is up, without changing them. Check that the
apps `Kustomization` lists them in its inventory:

```sh
kubectl get kustomization MC_NAME-clusters-WC_NAME-apps -n org-ORG_NAME -o yaml | yq '.status.inventory'
```

If the cluster's `Kustomization` already has `prune: true`, first give every object in `apps`, and in any other
directory that changes owner, the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation (`OCIRepository`s,
ConfigMaps and Secrets as well as `HelmRelease`s), and wait until Flux has applied it. Once each object is in its new
`Kustomization`'s inventory, take the annotation off again in Git. Keep it on the objects that carry it anyway, such
as the cluster's `HelmRelease`.

## Turn on pruning for the clusters

On `main`, every `Kustomization` has `prune: false`: deleting a file from Git leaves the object it created on the
cluster, unmanaged. Here, every `Kustomization` has `prune: true`, so deleting an app's files uninstalls the app, and a
handful of objects that must never go by accident carry the `kustomize.toolkit.fluxcd.io/prune: disabled`
annotation (see [Deletion protection](../explanation/deletion-protection.md)).

The base on `main` gives the cluster's `HelmRelease` the `giantswarm.io/prevent-deletion` label, but not the
annotation. With pruning on and only the label, deleting a cluster's files doesn't leave the cluster alone: Flux tries
to delete it, the management cluster refuses, and the `Kustomization` fails.

1. Give the cluster's `HelmRelease` and `OCIRepository` in your cluster base both the annotation and the label, as
   [bases/clusters/capa/cluster.yaml](/bases/clusters/capa/cluster.yaml) has them. Do the same for anything else your
   clusters' `Kustomization`s apply that must outlive its file. Push, and wait until Flux has applied it.
1. Set `prune: true` on the clusters' `Kustomization`s, `-direct` ones included, and push. Turning `prune` on deletes
   nothing that's still in the build: Flux only deletes what leaves it from now on.
1. Objects that left the build while `prune` was off aren't in any inventory, so Flux doesn't know about them and
   leaves them. Find and delete them by hand if you don't want them.

A `-direct` `Kustomization` with `prune: true` deletes what it applied in the workload cluster when you delete it,
which is what you want when you delete the cluster, and the reason
[Delete a workload cluster](./delete-cluster.md#remove-out-of-band-resources) removes it first.

## Install apps into their own namespace

On `main`, the `hello-world` and `cert-manager` examples install into `org-<organisation>` in the workload cluster,
which creates an organisation namespace there. Here, each app installs into a namespace of its own, `hello-world` and
`cert-manager`, with its Helm storage in the same namespace. The `HelmRelease`s stay in the organisation's namespace on
the management cluster. Apps of your own built from those examples can follow, or not: it's a choice, and it costs a
reinstall.

Flux uninstalls a release whose `targetNamespace` or `storageNamespace` changes, and installs it again in the new
namespace, in separate reconciliations. Until the new install is ready, the app isn't running:

- `hello-world` has no Service or `HTTPRoute` in between.
- cert-manager has no controller, and its webhook configurations go with the release, so the API server stores
  changes to `Certificate`s without validating them, and nothing acts on them until the reinstall.
- CRDs survive only if the chart keeps them. `cert-manager-app` does, with `cert-manager.crds.keep: true`, its default.
  With `keep` off, or for a chart whose CRDs don't have the `helm.sh/resource-policy: keep` annotation, the uninstall
  deletes the CRDs and every resource of those kinds.
- cert-manager reads the Secrets of `ClusterIssuer`s from its own namespace. Before you change it, copy the ACME
  account key, and any CA key pairs or credentials you created yourself, from `org-<organisation>` to `cert-manager` in
  the workload cluster. Otherwise the `ClusterIssuer`s aren't ready and renewals fail, and a missing ACME account key
  registers a new account.

Change `targetNamespace` and `storageNamespace` together, and keep `install.createNamespace: true`. The template's
cert-manager no longer installs its CRDs (`cert-manager.crds.enabled: false`), because the Giant Swarm release does.
The `org-<organisation>` namespace in the workload cluster isn't part of any release, so nothing deletes it: delete it
once it holds nothing you need.

## Replace App Sets and Cluster Templates

`main` has two kinds of base that this layout replaces:

| `main` | Here | Read |
| --- | --- | --- |
| `bases/app_sets`, listed in a cluster's `mapi/app_sets` | `bases/stacks`, listed in the cluster's `apps` or `cluster/apps` | [Stacks](../tutorials/intermediate/stacks.md) |
| `bases/cluster_templates`, with stages in `bases/environments/stages/*/hello_app_cluster` | A cluster base in `bases/clusters`, with stage and region Components | [Cluster bases](../tutorials/intermediate/cluster-bases.md), [Stages and regions](../tutorials/intermediate/stages-and-regions.md) |
| `bases/clusters/capa/template` | `bases/clusters/capa` | [Align the CAPA cluster base](#align-the-capa-cluster-base-optional) |
| `bases/apps/envoy-gateway`, three charts | `bases/stacks/envoy-gateway`, the `gateway-api-bundle` chart | [Move Envoy Gateway to the bundle](#move-envoy-gateway-to-the-bundle) |

Nothing forces you to move. `kubectl gs gitops add base` writes `bases/clusters/PROVIDER` from X.Y.Z on, and an
existing cluster that names `bases/clusters/capa/template` with `--base` keeps working.

> [!Caution]
> Keep one `HelmRelease` per release while you move. Two `HelmRelease`s for the same release, or a `HelmRelease` and
> an `App`, upgrade over each other without an error. See [One owner per object](../explanation/one-owner.md).

What matters when you do move is that the objects keep their names and their values. A `HelmRelease` that keeps its
name and namespace is updated in place; one whose name changes is a new release, and the old one is uninstalled. So
render each cluster before and after, and compare:

```sh
tools/fake-flux build CLUSTER_KUSTOMIZATION -M > /tmp/before.yaml
```

Make the change, then build again into `/tmp/after.yaml`, and compare the two with `diff`. The names of the
`HelmRelease`s and `OCIRepository`s, and the merged values, should be the same; labels and annotations may differ.
For a cluster from a Cluster Template, the stage's patches move into a stage Component that the cluster lists after
its region, and the template's own values into the cluster's `cluster_userconfig.yaml`, so that they come last.

## Move Envoy Gateway to the bundle

`main`'s `bases/apps/envoy-gateway` installs three charts, with a `HelmRelease` in Git for each. Giant Swarm supports
Envoy Gateway only as the `gateway-api-bundle`, so [bases/stacks/envoy-gateway](/bases/stacks/envoy-gateway/README.md)
installs that instead. The bundle creates the three `HelmRelease`s itself, under the names they had,
`${cluster_name}-gateway-api-crds`, `${cluster_name}-envoy-gateway` and `${cluster_name}-gateway-api-config`, and adds
`${cluster_name}-gateway-api-state-metrics`. A cluster's values keep their names too:
`${cluster_name}-<app>-user-values` and `${cluster_name}-<app>-user-secrets`. Of the base's defaults, only
`${cluster_name}-gateway-api-config-values` is still read. If you changed `default_config_gateway_api_crds.yaml` or
`default_config_envoy_gateway.yaml`, move those values into the app's `-user-values` ConfigMap, or they're gone after
the move, without an error.

The names stay, but the owner changes. Flux prunes the three `HelmRelease`s it applied from Git, and the bundle
creates them again. A pruned `HelmRelease` uninstalls its release, so in a single commit the move takes the Gateway
down, with its load balancer and its DNS records, and brings it back at a new address. To keep the releases running,
suspend them first: a suspended `HelmRelease` is deleted without uninstalling anything, and the one the bundle
creates then [adopts the release](./adopt-app.md#how-a-helmrelease-adopts-a-release) that's there.

The bundle sets the version of each app, and the adoption upgrades to it. Pick a bundle version whose apps are the
versions the cluster runs, or newer, from the table in the
[bundle's README](https://github.com/giantswarm/gateway-api-bundle#compatibility).

1. Suspend the three `HelmRelease`s, with a patch in the `kustomization.yaml` of the cluster's directory that lists
   `bases/apps/envoy-gateway`:

    ```yaml
    patches:
      - patch: |-
          - op: add
            path: /spec/suspend
            value: true
        target:
          kind: HelmRelease
          name: .*-(gateway-api-crds|envoy-gateway|gateway-api-config)
    ```

    Commit and push.

    **Check:** all three are suspended on the management cluster:

    ```sh
    kubectl get helmrelease -n org-${ORG_NAME} -o custom-columns='NAME:.metadata.name,SUSPENDED:.spec.suspend' | grep gateway
    ```

1. Only then list `bases/stacks/envoy-gateway` in that `kustomization.yaml` instead, and take the patch out. Commit
   and push.

    Flux deletes the three suspended `HelmRelease`s and their `OCIRepository`s, which have the names the bundle's
    have too. Until they're gone, the bundle's `HelmRelease`, `${cluster_name}-gateway-api-bundle`, fails with a
    message that they exist and can't be imported into its release. It retries, creates them, and each one upgrades
    the release it finds.

    **Check:** the bundle's `HelmRelease` is `Ready`, and the three say `Helm upgrade succeeded`. `Helm install
    succeeded` would mean a release was uninstalled and installed again:

    ```sh
    flux get helmreleases -n org-${ORG_NAME} | grep gateway
    ```

    If the bundle's `HelmRelease` says `Stalled` instead, the old objects took longer to go than its 10 install
    retries last. Once they're gone, start it again, with the cluster's name for `WC_NAME`:

    ```sh
    flux reconcile helmrelease WC_NAME-gateway-api-bundle -n org-${ORG_NAME} --reset
    ```

Try the two steps on a test cluster before you do them where the Gateway matters.

## Move charts to `gsoci.azurecr.io`

The template's apps take their charts from an `OCIRepository` on `gsoci.azurecr.io`, through `spec.chartRef`. A
`HelmRelease` of yours with `spec.chart`, reading a `HelmRepository` such as one of Giant Swarm's old app catalogs on
GitHub Pages, or a `GitRepository`, keeps working. Those catalogs aren't guaranteed to keep receiving new versions,
though, so move each app before you next need to upgrade it.

Change the source and nothing else. A `HelmRelease` whose release name, target namespace, storage namespace or chart
name changes on the way is uninstalled and installed again, and so is one with a new `metadata.name`.
[Move an app's chart to an `OCIRepository`](./move-app-to-oci.md) moves one app with an upgrade, in three
commits, and says how to check that it was one.
