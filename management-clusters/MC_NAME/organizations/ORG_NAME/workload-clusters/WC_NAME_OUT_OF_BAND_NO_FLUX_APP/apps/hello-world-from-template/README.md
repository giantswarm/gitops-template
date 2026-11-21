# WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world-from-template

hello-world from its App Template, [`bases/apps/hello-world`](/bases/apps/hello-world/), with values of this
cluster's own on top. The App Template holds what every cluster has; this directory holds only what's different here.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies it into `org-<name>` once the
cluster is up.

## What's here

- `kustomization.yaml`: lists the App Template, turns the values below into the
  `${cluster_name}-hello-world-user-values` ConfigMap, and makes hello-world wait for the cluster's Gateway API
  CRDs with `dependsOn`.
- `override_config_hello_world.yaml`: this cluster's values: more replicas, and the `hello` hostname that the
  cluster's envoy-gateway stack serves.

## When you copy it

Point `resources:` at your App Template and put your cluster's values in the override file. Keep the ConfigMap name
`${cluster_name}-<app>-user-values`: it's the name the App Template's `HelmRelease` reads. Drop the `dependsOn`
patch if the cluster has no envoy-gateway, or the release waits forever.

## Read more

- [Override values for one cluster](/docs/tutorials/intermediate/app-templates.md#override-values-for-one-cluster)
- [App values](/docs/reference/values.md#app-values)
