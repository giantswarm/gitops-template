# Move a running cluster to scheduled upgrades

A cluster made from a cluster base gets its release from the `release` variable of its `Kustomization`, and upgrades
as soon as you change it. To have it upgrade only in a window instead, move it to the layout of the
[WC_NAME_SCHEDULED_UPGRADES](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/)
example, where a Flux Operator `ResourceSet` renders the cluster's `OCIRepository` and `HelmRelease` at the release a
`ResourceSetInputProvider` picks. This page moves a running cluster without changing it: no upgrade, and above all no
deletion. [Hold upgrades for a window](../tutorials/advanced/scheduled-upgrades.md) explains how the example works.

## Before you start

The move hands the cluster's `OCIRepository` and `HelmRelease` from one owner to another. The cluster's
`Kustomization` lets go of them, which doesn't delete them, as both have the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation, and its `ResourceSet` takes them over once its provider has a
version. Forcing the provider picks the highest release in its range at once, outside the window, so pin the range to
the release the cluster runs first.

Export the names the commands use:

```sh
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
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
- You know the release the cluster runs: the `release` in its `Kustomization`, for example `36.2.0`.
- You can force a `ResourceSetInputProvider`, with the `flux-operator` CLI or `kubectl annotate`, see
  [Install before the first window](../tutorials/advanced/scheduled-upgrades.md#install-before-the-first-window).

## Move the cluster

1. Set the provider's `spec.filter.semver` to the cluster's current release, the `release` in its `Kustomization`, for
   example `'36.2.0'`. Move the cluster's files to the example's layout: copy `release-input-provider.yaml`,
   `cluster-resource-set.yaml` and `patch_delete_base_cluster.yaml` into the cluster's `cluster` directory, list them
   in its `kustomization.yaml` as the example does, and take `release` out of the cluster's `Kustomization`. Then
   commit and push.
1. Once Flux has applied the provider, force it as above. The `ResourceSet` takes over the `OCIRepository` and the
   `HelmRelease` at the release the cluster already runs, so the cluster doesn't change.

    ```sh
    flux-operator reconcile inputprovider ${WC_NAME}-release -n org-${ORG_NAME} --force
    ```

1. Set the range back, for example to `'>=36.0.0 <37.0.0'`, then commit and push. The cluster moves to the highest
   release in it at the next window.

**Check:** the `OCIRepository` and the `HelmRelease` carry the `resourceset.fluxcd.controlplane.io/name` label of
their `ResourceSet`, and the release hasn't changed:

```sh
kubectl get helmrelease,ocirepository ${WC_NAME} -n org-${ORG_NAME} -L resourceset.fluxcd.controlplane.io/name
flux get helmreleases ${WC_NAME} -n org-${ORG_NAME}
```
