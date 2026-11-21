# Move a fork to the kubectl-gs file and resource names

- [What changed](#what-changed)
- [Before you start](#before-you-start)
- [Rename the app files](#rename-the-app-files)
- [Rename the cluster user config](#rename-the-cluster-user-config)
- [Rename the workload cluster Kustomizations (optional)](#rename-the-workload-cluster-kustomizations-optional)
- [Align the CAPA cluster base (optional)](#align-the-capa-cluster-base-optional)
- [Record the layers](#record-the-layers)

This template uses the file and resource names that `kubectl gs gitops` generates. Earlier versions of the template
used names of their own, so `kubectl gs gitops check --adopt` skipped their apps, and `kubectl gs gitops add
automatic-update` and the `gitops upgrade` migrations couldn't find their files. Follow this guide if your repository
was forked from one of those versions.

## What changed

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

## Before you start

You need kubectl-gs 6.0.0 or newer, see [kubectl-gs version](../appendices.md#kubectl-gs-version).

Start from a clean clone of your repository, on a new branch:

```sh
git switch -c kubectl-gs-names
```

Every command below runs from the root of the clone.

## Rename the app files

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

## Rename the cluster user config

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
    repository runs the [CI validation](./ci-validation.md).

Flux creates the new ConfigMap and points the cluster's `HelmRelease` at it. The merged values stay the same. If the
workload cluster `Kustomization`s have `prune: true`, as in this template, Flux deletes the old `-user-config` ConfigMap
too. If they have `prune: false`, as in earlier versions, it stays on the management cluster. Delete it once the
cluster's `HelmRelease` is `Ready` again:

```sh
kubectl delete configmap WC_NAME-user-config -n org-ORG_NAME
```

## Rename the workload cluster Kustomizations (optional)

Renaming a Flux `Kustomization` creates a new one. If the `Kustomization` that applies it has `prune: true`, as in this
template, Flux deletes the old one. If it has `prune: false`, as in earlier versions, the old one stays, and both apply
the same resources until you delete it. The workload cluster `Kustomization`s are in the organisation's namespace,
`org-ORG_NAME`, and the organisation's namespace `Kustomization` applies them. If yours are still in `default`, and
the management cluster's `Kustomization` applies them, use `-n default` below, see
[Move the workload cluster Kustomizations](../reference/repo-structure.md#move-the-workload-cluster-kustomizations).

> **Warning:** check that the old workload cluster `Kustomization` has `prune: false` before you go on. Deleting a
> `Kustomization` with `prune: true` deletes what it applied, such as the cluster's apps, before the new one takes it
> over. The cluster's `HelmRelease` stays only if it has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation
> or the `giantswarm.io/prevent-deletion` label, see [How it works](../how-it-works.md).

1. Check the `prune` setting of the old `Kustomization`:

    ```sh
    kubectl get kustomization clusters-WC_NAME -n org-ORG_NAME -o jsonpath='{.spec.prune}'
    ```

    If it prints `true`, set `prune: false` in its file first, push, and wait until Flux has applied it.

1. Change `metadata.name` in
   `management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml` to
   `MC_NAME-clusters-WC_NAME`, and the same for `WC_NAME-direct.yaml` next to it if you have one. If your repository
   runs the [CI validation](./ci-validation.md), rename the `Kustomization` in the `gitops_ignored_objects` input of
   `.github/workflows/validate.yaml` and in the `kustomize.toolkit.fluxcd.io/name` labels of `tests/ats/assertions` too.

1. After you merge, Flux creates the new `Kustomization`. If the `Kustomization` that applies it has `prune: false`,
   delete the old one by hand:

    ```sh
    kubectl delete kustomization clusters-WC_NAME -n org-ORG_NAME
    ```

1. If you set `prune: false` in the first step, set `prune: true` again in the renamed file, and push.

## Align the CAPA cluster base (optional)

If your repository has its own copy of the CAPA cluster base, compare it with the
[one in this template](/bases/clusters/capa). It now has one `cluster.yaml` with the `OCIRepository` and the
`HelmRelease`, as `kubectl gs gitops add base --provider capa` writes. Merge your two files into it and change
`kustomization.yaml` to list `cluster.yaml`. The base's [readme](/bases/clusters/capa/readme.md) lists where
it differs from the CLI's on purpose.

## Record the layers

Once the files are renamed, `kubectl gs gitops` recognizes the apps.

1. See what it records:

    ```sh
    kubectl gs gitops check --adopt --dry-run
    ```

    Every app directory under `apps` is listed as an `app` layer. If the output lists directories under
    `Skipped`, they still lack a `helm-release.yaml` or a `kustomization.yaml`.

1. Record them in `.gitops-metadata.yaml`:

    ```sh
    kubectl gs gitops check --adopt
    ```

1. Commit and push:

    ```sh
    git add -A && git commit -m "Use the kubectl-gs file and resource names" && git push
    ```

From now on `kubectl gs gitops check` reports when the repository falls behind, and
`kubectl gs gitops add automatic-update` works on the apps. See [Repository structure](../reference/repo-structure.md#structure-version).
