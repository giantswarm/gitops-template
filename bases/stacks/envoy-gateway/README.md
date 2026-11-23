# envoy-gateway

`bases/stacks/envoy-gateway`

Envoy Gateway, so apps in a workload cluster can be reached over HTTPS through the Gateway API. It's installed as
Giant Swarm's `gateway-api-bundle`, the one way Giant Swarm supports: a chart that installs the apps Envoy Gateway is
made of, in a set order and at versions that work together.

It needs two things a Giant Swarm release doesn't set up:

- On AWS, the Gateway gets its address from the AWS Load Balancer Controller, which isn't part of a Giant Swarm
  release. Install Giant Swarm's `aws-lb-controller-bundle` on the workload cluster as
  [its README](https://github.com/giantswarm/aws-lb-controller-bundle#installing) describes, or ask Giant Swarm to.
- cert-manager's Gateway API support, for the Gateway's certificate:
  `global.apps.certManager.values.cert-manager.config.enableGatewayAPI: true` in the cluster's values, once the Gateway
  API CRDs are in, and a restart of cert-manager. Step 4 of the
  [basic tutorial](/docs/tutorials/basic/getting-started.md#4-deploy-an-app) does both in order.

Nothing applies this directory directly. A cluster or another stack lists it under `resources:`, and the Flux
`Kustomization` that applies that directory puts its objects into the organisation's namespace, `org-<name>`.

## What's here

- [`gateway-api-bundle/`](gateway-api-bundle/): the bundle's `oci-repository.yaml` (the chart and its version) and
  `helm-release.yaml`. The `HelmRelease` installs the bundle on the management cluster, in the organisation's
  namespace, as the `automation` account.
- `default_config_gateway_api_bundle.yaml`: the bundle's values. They name the workload cluster, and list the
  ConfigMaps and Secrets each app reads its values from, in the bundle's `extraConfigs`.
- `default_config_gateway_api_config.yaml`: the stack's default values for the Gateway. Its comments list what the
  workload cluster needs first.
- `kustomization.yaml`: lists the two objects and turns the two files of values into the
  `${cluster_name}-gateway-api-bundle-values` and `${cluster_name}-gateway-api-config-values` ConfigMaps.

The bundle creates a `HelmRelease` and an `OCIRepository` in the organisation's namespace for each of its apps, named
`${cluster_name}-<app>`. Those `HelmRelease`s install into the workload cluster through its
`${cluster_name}-kubeconfig` Secret, each waiting for the one before it with `dependsOn`:

1. `gateway-api-crds`: the Gateway API CRDs, into `kube-system`.
1. `envoy-gateway`: the Envoy Gateway controller, into `envoy-gateway-system`. Waits for the CRDs.
1. `gateway-api-config`: the `giantswarm-default` GatewayClass and Gateway. Waits for the controller.
1. `gateway-api-state-metrics`: metrics of the Gateway API objects. Waits for the CRDs.

Flux doesn't apply those objects from Git, the bundle does, so `flux trace` leads from one of them to the bundle's
`HelmRelease`, and the bundle's version decides the version of each app.

`dependsOn` orders installs and upgrades, but not deletes: when a `Kustomization` prunes the stack, the bundle deletes
its `HelmRelease`s and helm-controller uninstalls the apps at once. If Envoy Gateway is gone before it has cleared the
GatewayClass's finalizer, the GatewayClass stays `Terminating` and the uninstall of `gateway-api-config` waits for it.
That only matters when you remove the stack from a workload cluster that stays up. Clear the finalizer there with:

```sh
kubectl patch gatewayclass giantswarm-default --type=merge -p '{"metadata":{"finalizers":null}}'
```

## When you copy it

List the stack as it is, and give a cluster its own values for an app in `${cluster_name}-<app>-user-values`, as the
out-of-band examples' `cluster/apps/envoy-gateway-from-template/` do. Values for the bundle itself, such as
`apps.gatewayApiStateMetrics.enabled: false`, go in `${cluster_name}-gateway-api-bundle-user-values`. Keep the Gateway's
name, `giantswarm-default`: apps attach their `HTTPRoute`s to it.

Don't add a `HelmRelease` of your own for one of the bundle's charts next to it: two things would install one release,
see [One owner per object](/docs/explanation/one-owner.md).

## Read more

- [Stacks tutorial](/docs/tutorials/intermediate/stacks.md)
- [Order it after another release](/docs/tutorials/intermediate/app-templates.md#order-it-after-another-release)
