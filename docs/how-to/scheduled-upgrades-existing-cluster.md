# Move a running cluster to scheduled upgrades

A cluster made from a cluster base gets its release from the `release` variable of its Flux `Kustomization`, and
upgrades as soon as you change it. To have it upgrade only in a window instead, move it to the layout of the
[WC_NAME_SCHEDULED_UPGRADES](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/)
example, where a Flux Operator `ResourceSet` renders the cluster's `OCIRepository` and `HelmRelease` at the release a
`ResourceSetInputProvider` picks. This page moves a running cluster without changing it: no upgrade, and above all no
deletion. [Hold upgrades for a window](../tutorials/advanced/scheduled-upgrades.md) explains how the example works.

## Before you start

The move hands the cluster's `OCIRepository` and `HelmRelease` from one owner to another. The cluster's
`Kustomization` lets go of them, and its `ResourceSet` takes them over once its provider has a version. Letting go
doesn't delete them, as both have the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. Forcing the provider
picks the highest release in its range at once, outside the window, so first pin the range to the release the cluster
runs.

Export the names the commands use, and run them from the root of your clone:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export ORG_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}
export WC_DIR=${ORG_DIR}/workload-clusters/${WC_NAME}
export EXAMPLE_DIR=management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/cluster
```

Check that:

- Flux has applied the current cluster base, so that the cluster's live `OCIRepository` has the
  `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. Without it, the move tries to prune the `OCIRepository`,
  which the `giantswarm.io/prevent-deletion` label refuses, and the prune fails:

    ```sh
    kubectl get ocirepository ${WC_NAME} -n org-${ORG_NAME} \
      -o jsonpath='{.metadata.annotations.kustomize\.toolkit\.fluxcd\.io/prune}'
    ```

    It has to print `disabled`.
- You know the release the cluster runs, the `release` in its `Kustomization`, and the revision of its Helm release,
  to compare with at the end:

    ```sh
    export RELEASE=$(yq '.spec.postBuild.substitute.release' ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml)
    kubectl get helmrelease ${WC_NAME} -n org-${ORG_NAME} -o jsonpath='{.status.history[0].version}'
    ```

- You can force a `ResourceSetInputProvider`, with the `flux-operator` CLI or `kubectl annotate`, see
  [Install before the first window](../tutorials/advanced/scheduled-upgrades.md#install-before-the-first-window).

## The cluster's own values

The cluster's `HelmRelease` takes its values from the ConfigMaps in its `valuesFrom`, in order. Three places write that
list: the cluster base, a Component such as the region, and the patches in the cluster's own `kustomization.yaml`, such
as `patch_cluster_userconfig.yaml`, which appends `${cluster_name}-cluster-userconfig`.

After the move, the `HelmRelease` is one of the `resources` of the `ResourceSet`, and kustomize no longer sees a
`HelmRelease` there. A patch aimed at the `HelmRelease` matches nothing, and kustomize is silent about a patch that
matches nothing: the build succeeds and the entry is gone. Flux Operator then applies the `HelmRelease` it
renders, and replaces `valuesFrom` whole. Forcing the provider would upgrade the cluster without its own values, which
for node pool settings means new nodes.

So the move carries every entry across, in two ways:

- The base's entries and the region's are written out in the example's `ResourceSet`, as they are for a new scheduled
  cluster. The region's entry fits any region, as every region names its ConfigMap `${cluster_name}-region-config`.
- The cluster's own entries come from a patch on the `ResourceSet`, the example's `patch_cluster_userconfig.yaml`. It's
  a JSON 6902 patch that appends to `/spec/resources/1/spec/valuesFrom/-`, the `HelmRelease` being the second of the
  `resources`. A `test` operation first checks that the second resource is the `HelmRelease`, so the build fails,
  rather than patching the `OCIRepository`, if someone reorders them.

Anything else that targets the cluster's `HelmRelease` or `OCIRepository` stops matching too: an extra node pool
Component, your own patches, and a stage's release pin. The provider's range is the pin from now on. Step 2 below
compares the lists before anything reaches the cluster, so a missed entry shows up there.

## Move the cluster

1. Copy the example's files into the cluster's `cluster` directory, pin the provider's range to the release the
   cluster runs, list the files in the cluster's `kustomization.yaml`, and take `release` out of the cluster's
   `Kustomization`. The example's `patch_cluster_userconfig.yaml` replaces the cluster's own, and its target moves from
   the `HelmRelease` to the `ResourceSet`. A cluster without values of its own has no `patch_cluster_userconfig.yaml`,
   and gets none:

    ```sh
    cp ${EXAMPLE_DIR}/release-input-provider.yaml ${EXAMPLE_DIR}/cluster-resource-set.yaml \
      ${EXAMPLE_DIR}/patch_delete_base_cluster.yaml ${WC_DIR}/cluster/
    if [ -f ${WC_DIR}/cluster/patch_cluster_userconfig.yaml ]; then
      cp ${EXAMPLE_DIR}/patch_cluster_userconfig.yaml ${WC_DIR}/cluster/
    fi
    yq -i '.spec.filter.semver = strenv(RELEASE)' ${WC_DIR}/cluster/release-input-provider.yaml
    yq -i '.resources += ["release-input-provider.yaml", "cluster-resource-set.yaml"] |
      .patches = [{"path": "patch_delete_base_cluster.yaml"}] + (.patches // []) |
      (.patches[] | select(.path == "patch_cluster_userconfig.yaml") | .target) =
        {"group": "fluxcd.controlplane.io", "kind": "ResourceSet", "name": "\\${cluster_name}"}' \
      ${WC_DIR}/cluster/kustomization.yaml
    yq -i 'del(.spec.postBuild.substitute.release)' ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml
    ```

    If the cluster's `kustomization.yaml` has other patches on its `HelmRelease`, rewrite them the way
    `patch_cluster_userconfig.yaml` is written: JSON 6902, with paths under `/spec/resources/1`, the `test` first, and
    the `ResourceSet` as the target.

1. Compare the `valuesFrom` of the running `HelmRelease` with the one the `ResourceSet` will render. kustomize leaves
   `${cluster_name}` for Flux to fill in, so `sed` does it here:

    ```sh
    diff <(kubectl get helmrelease ${WC_NAME} -n org-${ORG_NAME} -o yaml | yq '.spec.valuesFrom') \
      <(kubectl kustomize ${WC_DIR}/cluster |
        yq 'select(.kind == "ResourceSet") | .spec.resources[] | select(.kind == "HelmRelease") | .spec.valuesFrom' |
        sed "s/\${cluster_name}/${WC_NAME}/g")
    ```

    It has to print nothing. A line marked `<` is an entry the move loses: add it to `patch_cluster_userconfig.yaml` as
    another `add` on the same path, in the order the running `HelmRelease` lists it, and compare again. Don't go on
    until the lists match.

1. Commit and push.
1. Once Flux has applied the provider, force it. The `ResourceSet` takes over the `OCIRepository` and the
   `HelmRelease` at the release the cluster already runs, with the same values, so the cluster doesn't change:

    ```sh
    flux-operator reconcile inputprovider ${WC_NAME}-release -n org-${ORG_NAME} --force
    ```

1. Set the range back, for example to `'>=36.0.0 <37.0.0'`, then commit and push. The cluster moves to the highest
   release in it at the next window.

**Check:** the `OCIRepository` and the `HelmRelease` carry the `resourceset.fluxcd.controlplane.io/name` label of
their `ResourceSet`, and the release hasn't been upgraded: its revision is the one you noted before you started.

```sh
kubectl get helmrelease,ocirepository ${WC_NAME} -n org-${ORG_NAME} -L resourceset.fluxcd.controlplane.io/name
flux get helmreleases ${WC_NAME} -n org-${ORG_NAME}
kubectl get helmrelease ${WC_NAME} -n org-${ORG_NAME} -o jsonpath='{.status.history[0].version}'
```

If it doesn't get there, see [When something isn't Ready](./troubleshooting.md).

The repository's tests make the same move on the `WC_NAME` example: `tests/ats/test_cluster_move.py` builds it without
a cluster and fails if a `valuesFrom` entry goes missing, and the kind test moves the cluster and checks that
the `ResourceSet` takes it over with the same values, chart and tag, see [The kind test](../reference/ci-checks.md#flux-operator).
