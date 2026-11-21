# Change an app

Every change to an app is a change to one of its files, pushed to Git. The trick is knowing which file:

| To change | Edit | Resource |
| --- | --- | --- |
| the chart version | `oci-repository.yaml` | the `OCIRepository` |
| how the chart is installed, such as the target namespace, timeouts or retries | `helm-release.yaml` | the `HelmRelease` |
| plain values | `override_config.yaml` | the `-user-values` ConfigMap the app's `kustomization.yaml` generates |
| secret values | your secret manager, or `secret.enc.yaml` | the `-user-secrets` Secret |

The values ConfigMap and Secret carry the `reconcile.fluxcd.io/watch: Enabled` label, so Flux applies a change to them
as soon as it's merged, not at the `HelmRelease`'s next `interval`. Keep the label on every ConfigMap and Secret a
`HelmRelease` lists in `valuesFrom`: CI fails without it.

For an app from an [App Template](../tutorials/intermediate/app-templates.md), `oci-repository.yaml` and
`helm-release.yaml` are part of the template. Changing them there changes the app in every cluster that uses the
template. To change them for one cluster, add a patch to the app's `kustomization.yaml`, see
[Add an app from an App Template](./add-app.md#add-an-app-from-an-app-template). The same goes for an app from a
stack.

Export the names the commands use, and go to the app's directory:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

A base app is in `cluster/apps/${APP_NAME}` instead.

## Change the chart version

Set the new chart version in the `OCIRepository`:

```sh
yq -i '.spec.ref.tag = "NEW_VERSION"' oci-repository.yaml
```

Commit and push. Flux pulls the chart once the `OCIRepository` has fetched the new tag, and upgrades the release.

If a stage pins the app's version, as the stages in [bases/environments/stages](/bases/environments/stages/) do, the
stage's patch wins: change the version there, see
[Promote a change from dev to prod](../tutorials/intermediate/stages-and-regions.md#promote-a-change-from-dev-to-prod).
To have Flux pick up new versions by itself, use a version range instead, see
[Let Flux install new chart versions](../tutorials/intermediate/automatic-updates.md).

## Change how the chart is installed

Edit `helm-release.yaml`. The [HelmRelease documentation](https://fluxcd.io/flux/components/helm/helmreleases/)
lists every field. Two need care on a running app:

- `releaseName`, `targetNamespace` and `storageNamespace` name the Helm release. Changing one installs a new release
  next to the old one, rather than moving it.
- `kubeConfig` points the release at the workload cluster. Without it, the chart installs into the management cluster.

## Change the values

Edit `override_config.yaml`, then commit and push. Only the keys you set change; the rest comes from the earlier layers,
see [App values](../reference/values.md#app-values).

If the app has no `override_config.yaml` yet, create it and add the `configMapGenerator` to the app's
`kustomization.yaml`, as [Add an app directly](./add-app.md#add-an-app-directly) shows.

**Check:** the release is `Ready` again, at a new revision:

```sh
flux get helmreleases ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
```

## Change secret values

Where you change them depends on where they come from:

- From your secret manager, through an `ExternalSecret`: change the value there, see
  [Change a secret value](./external-secrets.md#change-a-secret-value). Nothing changes in Git.
- From a SOPS-encrypted `secret.enc.yaml`: decrypt, change and encrypt the file with the cluster's private key, see
  [Change encrypted values](./sops.md#change-encrypted-values).
