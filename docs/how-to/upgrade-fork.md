# Bring an older fork up to date

A fork of this template doesn't follow the template by itself. When the template changes its layout or its names, a
fork made before the change keeps working, but it drifts: `kubectl gs gitops` stops recognising parts of it, and the
docs describe a repository it no longer is. This page brings it back in line.

Work through the sections in order. Each one says what it changes on a running management cluster, and the ones that
move objects Flux manages say how to move them without deleting anything. Read those twice before you push.

- [Check and upgrade the structure version](#check-and-upgrade-the-structure-version)
- [Move to the kubectl-gs names](#move-to-the-kubectl-gs-names)
- [Move an organisation's namespace objects](#move-an-organisations-namespace-objects)
- [Move the workload cluster Kustomizations](#move-the-workload-cluster-kustomizations)

## Check and upgrade the structure version

The repository's layout has a version, the [structure version](../reference/repo-structure.md#structure-version),
which `kubectl gs gitops` records in `.gitops-metadata.yaml`. `check` and `upgrade` need kubectl-gs 6.0.0 or newer,
see [kubectl-gs version](../reference/tools.md#kubectl-gs-version). If yours is older, update it with
`kubectl gs selfupdate`.

To see which parts of your repository are behind, run this in your clone:

```sh
kubectl gs gitops check
```

It exits with an error when anything is behind, so you can run it in CI. If your repository is older than the
metadata file, run `kubectl gs gitops check --adopt` once to record what's there as current. It assumes what's there
is current, so it can't find drift from before you ran it.

To see what it would record first:

```sh
kubectl gs gitops check --adopt --dry-run
```

Every app directory under `apps` is listed as an `app` layer. If the output lists directories under `Skipped`, they
still lack a `helm-release.yaml` or a `kustomization.yaml`: rename them first, see
[Move to the kubectl-gs names](#move-to-the-kubectl-gs-names). Then record them in `.gitops-metadata.yaml`:

```sh
kubectl gs gitops check --adopt
```

From now on `kubectl gs gitops check` reports when the repository falls behind, and
`kubectl gs gitops add automatic-update` works on the apps.

To bring the repository up to date, first see which files would change:

```sh
kubectl gs gitops upgrade --dry-run
```

Then run the upgrade:

```sh
kubectl gs gitops upgrade
```

It changes the files in place and keeps your own edits where it can. Review the result with `git diff` before you
commit it. If something goes wrong, undo it with Git. That's why the command doesn't run on a repository with
uncommitted changes, or on a directory Git doesn't track, unless you pass `--force`. Migrations never touch files Git
ignores, such as decrypted secrets, so move those yourself.

Version 2 deploys clusters and apps with Flux `HelmRelease`s instead of App CRs. The upgrade to it doesn't convert
App CRs, because the `HelmRelease` has to take over the Helm release the App CR installed in the cluster. It fails on
every layer that still deploys or patches an App CR. Move those first, see the
[App Platform deprecation](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/).
Then it rewrites the user config patch of each workload cluster for the `HelmRelease`.

Version 3 drops the `mapi` directory of workload clusters. Its `cluster`, `apps` and any other directories move up
into the cluster's directory, next to `out-of-band`, and the cluster's `kustomization.yaml` lists what the cluster's
Kustomizations apply, never `out-of-band`, see
[Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations). It also moves everything
an organisation keeps in its namespace into the organisation's `namespace` directory, which its own Kustomization,
`namespace.yaml`, applies, see [Move an organisation's namespace objects](#move-an-organisations-namespace-objects).
The workload clusters' Kustomizations stay in `workload-clusters`, but `namespace.yaml` applies them too, into the
organisation's namespace, with their SOPS keys in `namespace/secrets`, see
[Move the workload cluster Kustomizations](#move-the-workload-cluster-kustomizations).
kubectl-gs doesn't know version 3 yet: `kubectl gs gitops add workload-cluster` still generates `mapi`, the version 2
layout, and `kubectl gs gitops upgrade` has no migration to version 3. Move an existing cluster by hand, as the
[CHANGELOG](/CHANGELOG.md) describes.

The CHANGELOG's "To split a running cluster's `Kustomization`" and "To move a running cluster" steps keep every
object while it changes owner.

Note that layers recorded without a structure version can't be upgraded. If you know the version they were created
with, set their `structureVersion` by hand. Otherwise, remove their entries and run
`kubectl gs gitops check --adopt`.

## Move to the kubectl-gs names

This template uses the file and resource names that `kubectl gs gitops` generates. Earlier versions of the template
used names of their own, so `kubectl gs gitops check --adopt` skipped their apps, and
`kubectl gs gitops add automatic-update` and the `gitops upgrade` migrations couldn't find their files. Follow this
section if your repository was forked from one of those versions.

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
| The envoy-gateway stack | `helmreleases.yaml`, `ocirepositories.yaml` | one directory per chart |

`kubectl gs gitops` relies on the app and cluster user config names. It doesn't read the `Kustomization` names or
the files of the cluster base, so renaming those is optional and only makes your repository look like what
`kubectl gs gitops add` creates.

### Before you start

You need kubectl-gs 6.0.0 or newer, see [kubectl-gs version](../reference/tools.md#kubectl-gs-version).

Start from a clean clone of your repository, on a new branch:

```sh
git switch -c kubectl-gs-names
```

Every command below runs from the root of the clone.

### Rename the app files

1. Rename the files everywhere in the repository: the apps of the workload clusters, the App Templates under
   `bases/apps`, and the cluster bases under `bases/clusters`, which you can merge into one file later, see
   [Align the CAPA cluster base](#align-the-capa-cluster-base-optional):

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
   it into a directory per chart, each with a `helm-release.yaml` and an `oci-repository.yaml`. See
   [bases/stacks/envoy-gateway](/bases/stacks/envoy-gateway/kustomization.yaml).

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

### Rename the workload cluster Kustomizations (optional)

Renaming a Flux `Kustomization` creates a new one. If the `Kustomization` that applies it has `prune: true`, as in this
template, Flux deletes the old one. If it has `prune: false`, as in earlier versions, the old one stays, and both apply
the same resources until you delete it. A fork old enough to need this section still has its workload cluster
`Kustomization`s in `default`, which the management cluster's `Kustomization` applies, so the commands below use
`-n default`. Rename them before you
[move the workload cluster Kustomizations](#move-the-workload-cluster-kustomizations). If you have already moved
them into the organisation's namespace, use `-n org-ORG_NAME` instead.

> [!Caution]
> Check that the old workload cluster `Kustomization` has `prune: false` before you go on. Deleting a
> `Kustomization` with `prune: true` deletes what it applied, such as the cluster's apps, before the new one takes it
> over. The cluster's `HelmRelease` stays only if it has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation
> or the `giantswarm.io/prevent-deletion` label, see
> [The protected objects](../explanation/deletion-protection.md#the-protected-objects).

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

Once the files are renamed, `kubectl gs gitops` recognises the apps. Record them as
[Check and upgrade the structure version](#check-and-upgrade-the-structure-version) describes, then commit and push:

```sh
git add -A && git commit -m "Use the kubectl-gs file and resource names" && git push
```

## Move an organisation's namespace objects

On a management cluster that already runs the repository, moving objects from what `MC_NAME.yaml` applies into the
organisation's `namespace` directory deletes them once. Flux deletes what leaves a `Kustomization`'s inventory in the
same reconciliation, and `MC_NAME.yaml` always applies a commit before the organisation's namespace `Kustomization`,
whose `dependsOn` names it, creates the objects again. Deleting the
`-direct` `Kustomization` deletes what it applied in the workload cluster, and deleting an `ExternalSecret` deletes the
Secret it wrote.

To move them without a deletion, use three commits, and let Flux apply each one before you push the next:

1. Annotate every object that moves with `kustomize.toolkit.fluxcd.io/prune: disabled`. `MC_NAME.yaml` applies the
   annotation, so Flux leaves the objects when they leave its inventory.
1. Move the objects into `namespace`, or into `multicluster/secret-stores` for the workload clusters' secret stores,
   which `namespace/kustomization.yaml` lists as `../multicluster/secret-stores`, add `namespace.yaml`, and take them
   out of the organisation's `kustomization.yaml`, as in
   [Add an organization](../tutorials/basic/getting-started.md#2-add-an-organisation). The workload clusters'
   `Kustomization`s, `-direct` ones included, move with the steps of
   [Move the workload cluster Kustomizations](#move-the-workload-cluster-kustomizations) instead. `MC_NAME.yaml` applies
   the commit first: it leaves the annotated objects where they are and creates `namespace.yaml`'s `Kustomization`,
   which then takes the objects over.
1. Remove the annotation, so Flux deletes the objects again when you delete them from Git. Leave it on SOPS key
   Secrets, such as a `-direct` `Kustomization`'s key in `namespace/secrets`: like the ones in `MC_NAME/secrets`,
   they keep `kustomize.toolkit.fluxcd.io/prune: disabled` for good, from `namespace/secrets/kustomization.yaml`.

A new management cluster needs none of this: its organisations' namespaces don't exist yet.

## Move the workload cluster Kustomizations

The workload clusters' Kustomizations, `WC_NAME.yaml`, `WC_NAME-apps.yaml` and the others, used to be in `default`:
`MC_NAME.yaml` applied the organisation's `workload-clusters` directory, and the cluster keys were in
`MC_NAME/secrets`. Their files stay where they are, but `namespace.yaml` applies them instead, into the organisation's
namespace. On a management cluster that already runs them, move them in two commits, and let Flux apply the first
before you push the second. Before you start:

- The organisation's `namespace.yaml` runs, see [Move an organisation's namespace objects](#move-an-organisations-namespace-objects).
- kustomize-controller supports `spec.deletionPolicy`: `kubectl explain kustomization.spec.deletionPolicy` describes
  it. The Flux of Giant Swarm management clusters does.
- Move each cluster's Kustomizations together: the apps Kustomization names its cluster's in `dependsOn`, in its own
  namespace.

> **Warning:** don't move the `Kustomization`s without the first commit. Flux deletes the old ones in `default` when
> their files leave `MC_NAME.yaml`'s build, and their finalizer deletes what they applied before the new ones in the
> organisation's namespace exist. Every app on the workload clusters would be uninstalled, and the clusters' values,
> `ExternalSecret`s and the Secrets they wrote, `PushSecret`s and application teams' `Kustomization`s would go. Only
> the clusters' `HelmRelease`s and `OCIRepository`s would stay. `deletionPolicy: Orphan` makes the finalizer delete
> nothing.

Export the names the commands below use:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export ORG_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}
```

1. The first commit moves nothing:

    - Add `deletionPolicy: Orphan` to every `Kustomization` in the organisation's `workload-clusters`. A `-direct` one
      there is a legacy cluster's, which stays in `default`, so leave it out:

      ```sh
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        case "$(basename ${f})" in
          kustomization.yaml | *-direct.yaml) ;;
          *) yq -i '.spec.deletionPolicy = "Orphan"' ${f} ;;
        esac
      done
      ```

    - Add the rule for the workload clusters' keys in `namespace/secrets` to `.sops.yaml`, ahead of the other rules,
      so an organisation key's rule for `namespace/secrets` can't take them, see
      [SOPS keys](../reference/sops-keys.md#encryption-rules):

      ```sh
      export MASTER_KEY_FP=$(gpg --show-keys --with-colons management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc |
        awk -F: '/^fpr/{print $10; exit}')
      yq -i '.creation_rules = [{
        "encrypted_regex": "^(data|stringData)$",
        "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/[^/]+/namespace/secrets/.*\\.(gpg|age)key\\.enc\\.yaml",
        "pgp": "'"${MASTER_KEY_FP}"'"
      }] + .creation_rules' .sops.yaml
      ```

    - Copy each key Secret those `Kustomization`s name in `decryption.secretRef` into the organisation's
      `namespace/secrets`, in the organisation's namespace, and list it in `namespace/secrets/kustomization.yaml`. If
      the organisation doesn't have that directory yet, create it as in
      [Add an organization](./sops.md#add-a-workload-cluster-key-gpg), with
      its `kustomization.yaml`, and list `secrets` in `namespace/kustomization.yaml`. With the master private key in
      your keyring, for each key file, such as `WC_NAME.gpgkey.enc.yaml`:

      ```sh
      export KEY_FILE=WC_NAME.gpgkey.enc.yaml
      sops --decrypt management-clusters/${MC_NAME}/secrets/${KEY_FILE} |
        yq '.metadata.namespace = "org-'"${ORG_NAME}"'"' > ${ORG_DIR}/namespace/secrets/${KEY_FILE}
      sops --encrypt --in-place ${ORG_DIR}/namespace/secrets/${KEY_FILE}
      yq -i '.resources += [strenv(KEY_FILE)]' ${ORG_DIR}/namespace/secrets/kustomization.yaml
      ```

   Push, and wait until `MC_NAME-gitops` and `MC_NAME-organization-ORG_NAME` are `Ready` at this revision. Check
   that every old `Kustomization` prints `Orphan`, and that the keys are in the organisation's namespace:

    ```sh
    kubectl get kustomization -n default -o custom-columns=NAME:.metadata.name,DELETION:.spec.deletionPolicy
    kubectl get secret -n org-${ORG_NAME} -l giantswarm.io/prevent-deletion=true
    ```

1. The second commit moves the `Kustomization`s:

    - Take `workload-clusters` and the replacement with `labelSelector: giantswarm.io/health-check-cluster=true` out
      of the organisation's `kustomization.yaml`, and list `../workload-clusters` in `namespace/kustomization.yaml`
      instead. `workload-clusters/kustomization.yaml` keeps listing the `Kustomization` files.
    - Change each file as [Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations) describes:
      no `metadata.namespace` and no `giantswarm.io/health-check-cluster` label, `sourceRef.namespace: default`,
      `organization: "${organization}"`, `org-${organization}` as the namespace of a `Cluster` health check, the
      organisation's namespace `Kustomization` in `dependsOn` where there's no `dependsOn` yet, and no
      `deletionPolicy`:

      ```sh
      export ORG_KUSTOMIZATION=$(yq '.metadata.name' ${ORG_DIR}/namespace.yaml)
      yq -i '.resources |= ((. // []) + ["../workload-clusters"] | unique)' ${ORG_DIR}/namespace/kustomization.yaml
      yq -i 'del(.resources[] | select(. == "workload-clusters")) |
        del(.replacements[] | select(.targets[].select.labelSelector == "giantswarm.io/health-check-cluster=true"))' \
        ${ORG_DIR}/kustomization.yaml
      for f in ${ORG_DIR}/workload-clusters/*.yaml; do
        case "$(basename ${f})" in kustomization.yaml | *-direct.yaml) continue ;; esac
        yq -i 'del(.metadata.namespace, .metadata.labels["giantswarm.io/health-check-cluster"], .spec.deletionPolicy) |
          del(.metadata.labels | select(length == 0)) |
          .spec.sourceRef.namespace = "default" | .spec.postBuild.substitute.organization = "${organization}" |
          with(.spec | select(has("healthChecks")) | .healthChecks[] | select(.kind == "Cluster");
            .namespace = "org-${organization}") |
          with(.spec | select(has("dependsOn") | not);
            .dependsOn = [{"name": strenv(ORG_KUSTOMIZATION), "namespace": "default"}])' ${f}
      done
      ```

    - A legacy `-direct` `Kustomization`, which stays in `default`, can't stay in `workload-clusters`, where
      `namespace.yaml` would put it in the organisation's namespace: move its file into the organisation's directory,
      take it out of `workload-clusters/kustomization.yaml`, and list it in the organisation's `kustomization.yaml`.
      `MC_NAME.yaml` keeps applying it. A `-direct` one in `namespace/workload-clusters`, from
      [Move an organisation's namespace objects](#move-an-organisations-namespace-objects), moves into
      `workload-clusters` and its list instead: `namespace.yaml` applies it from both, so it keeps its owner.
    - Take the keys you copied out of `MC_NAME/secrets/kustomization.yaml`, and `git rm` their files there. Keep a key
      that a legacy `-direct` `Kustomization` in `default` still uses.

   Push. `MC_NAME.yaml` deletes the old `Kustomization`s, which leave what they applied, and leaves the old keys in
   `default`, as they have `kustomize.toolkit.fluxcd.io/prune: disabled`. `namespace.yaml` then creates the new
   `Kustomization`s, which decrypt with the keys the first commit put in the organisation's namespace and take over
   the objects without changing them: the `HelmRelease`s don't upgrade, and nothing is uninstalled. Check that the new
   ones are `Ready`, that none of the old ones is left, and that the objects name their new owner's namespace:

    ```sh
    flux get kustomizations -n org-${ORG_NAME}
    kubectl get kustomization -n default
    kubectl get helmrelease -n org-${ORG_NAME} -L kustomize.toolkit.fluxcd.io/namespace
    ```

1. Once nothing in `default` uses them, delete the old keys from `default` by hand. For each one, remove its label
   first:

    ```sh
    kubectl label secret -n default KEY_SECRET giantswarm.io/prevent-deletion-
    kubectl delete secret -n default KEY_SECRET
    ```

The files don't move, so the `path`s and the per-cluster rules in `.sops.yaml` stay as they are. The new
`Kustomization`s run as the organisation's `automation` ServiceAccount, which may write only in the organisation's
namespace: a cluster directory that applies anything else fails with "forbidden", see
[Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations).
