# Change an app

This page changes an app that's already running: its chart version, how it's installed, its values or its secrets.
Every change is an edit to one of the app's files, pushed to Git. The trick is knowing which file:

| To change | Edit | Resource |
| --- | --- | --- |
| the chart version | `oci-repository.yaml` | the `OCIRepository` |
| the chart version of a [scheduled](../tutorials/advanced/scheduled-upgrades.md) or [multicluster](../tutorials/advanced/multicluster-apps.md) app | `spec.filter.semver` in its `input-provider.yaml` | the `ResourceSetInputProvider` |
| how the chart is installed, such as the target namespace, timeouts or retries | `helm-release.yaml` | the `HelmRelease` |
| plain values | `override_config.yaml` | the `-user-values` ConfigMap the app's `kustomization.yaml` generates |
| secret values | your secret manager, or `secret.enc.yaml` | the `-user-secrets` Secret |

The values ConfigMap and Secret carry the `reconcile.fluxcd.io/watch: Enabled` label, so Flux applies a change to them
as soon as it's merged, not at the `HelmRelease`'s next `interval`. Keep the label on every ConfigMap and Secret a
`HelmRelease` lists in `valuesFrom`: CI fails without it.

For an app from an [App Template](../tutorials/intermediate/app-templates.md), `oci-repository.yaml` and
`helm-release.yaml` are part of the template. Changing them there changes the app in every cluster that uses the
template. To change them for one cluster, add a patch to the app's `kustomization.yaml`, as
[Add an app from an App Template](./add-app.md#add-an-app-from-an-app-template) shows. The same goes for an app from a
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
stage's patch wins, so change the version there (see
[Promote a change from dev to prod](../tutorials/intermediate/stages-and-regions.md#promote-a-change-from-dev-to-prod)).
To have Flux pick up new versions by itself, use a version range instead:
[Let Flux install new chart versions](../tutorials/intermediate/automatic-updates.md) shows how.

A scheduled or multicluster app has no `oci-repository.yaml`: its `ResourceSet` renders the `OCIRepository` at the
version its provider exports. Change the provider's range, `spec.filter.semver` in `input-provider.yaml`, instead. Like
a new version, a new range reaches the app at the provider's next window (see
[How the window works](../tutorials/advanced/scheduled-upgrades.md#how-the-window-works)).

## Back out a version

Flux rolls back a failed upgrade on its own. This section is for one that succeeded and then misbehaved.

For an app with an `oci-repository.yaml`, set the last good version as the tag, as in
[Change the chart version](#change-the-chart-version), then commit and push.

For a scheduled or multicluster app, pin the provider to the last good version, then make it read the registry at
once, because a pin waits for the window too. Work in the app's directory (`multicluster/apps/APP_NAME` for a
multicluster app). `PROVIDER_NAME` is the provider's `metadata.name`, with `${cluster_name}` filled in:

1. Pin the range, then commit and push:

    ```sh
    yq -i '.spec.filter.semver = "LAST_GOOD_VERSION"' input-provider.yaml
    git commit -am "Back out ${APP_NAME} to LAST_GOOD_VERSION" && git push
    ```

1. Wait until Flux has applied the pin (the first command prints it), then force the provider. The provider exports
   the pinned version, and the `ResourceSet` moves every cluster it renders for back to it:

    ```sh
    kubectl get resourcesetinputprovider PROVIDER_NAME -n org-${ORG_NAME} -o jsonpath='{.spec.filter.semver}'
    flux-operator reconcile inputprovider PROVIDER_NAME -n org-${ORG_NAME} --force
    ```

Put the range back once a fixed version is out; it reaches the app at the next window.

## Change how the chart is installed

Edit `helm-release.yaml`. The [HelmRelease documentation](https://fluxcd.io/flux/components/helm/helmreleases/)
lists every field. Two need care on a running app:

- `releaseName`, `targetNamespace` and `storageNamespace` name the Helm release. Changing one installs a new release
  next to the old one, rather than moving it.
- `kubeConfig` points the release at the workload cluster. Without it, the chart installs into the management cluster.

## Correct changes made by hand

Flux sets back any hand change to what its `Kustomization`s apply, the `HelmRelease` and its values included. What the
chart installs in the workload cluster belongs to helm-controller, which by default doesn't look at it again once it's
installed: a `kubectl edit` on the app's Deployment stays until the chart or its values change. To have helm-controller
compare the release with what runs in the cluster, set `spec.driftDetection` in `helm-release.yaml`:

```yaml
spec:
  driftDetection:
    # `warn` only reports what differs; `enabled` sets it back
    mode: enabled
    ignore:
      # the HorizontalPodAutoscaler sets the replica count
      - paths: ["/spec/replicas"]
        target:
          kind: Deployment
```

It's off in the bases on purpose. With it on, helm-controller checks every object of the release against the workload
cluster at each `interval` and sets back anything that differs. That includes what something in the cluster changes on
purpose, such as an autoscaler's replica count or a field an operator or a webhook fills in. Each of those needs an
`ignore` rule, or helm-controller and the other party take turns at it for ever. Start with `warn`, read what it
reports in the `HelmRelease`'s events, add the rules, then switch to `enabled`.

## Change the values

Edit `override_config.yaml`, then commit and push. Only the keys you set change; the rest comes from the earlier layers
(see [App values](../reference/values.md#app-values)).

If the app has no `override_config.yaml` yet, create it and add the `configMapGenerator` to the app's
`kustomization.yaml`, as [Add an app directly](./add-app.md#add-an-app-directly) shows.

**Check:** the release is `Ready` again, at a new revision:

```sh
flux get helmreleases ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
```

If it doesn't get there, see [When something isn't Ready](./troubleshooting.md).

## Change secret values

Where you change them depends on where they come from:

- From your secret manager, through an `ExternalSecret`: change the value there, as
  [Change a secret value](./external-secrets.md#change-a-secret-value) describes. Nothing changes in Git.
- From a SOPS-encrypted `secret.enc.yaml`: decrypt the file with the cluster's private key, change it and encrypt it
  again, as [Change encrypted values](./sops.md#change-encrypted-values) describes.
