# bases/stacks/envoy-gateway

Envoy Gateway, so apps in a workload cluster can be reached over HTTPS through the Gateway API. It's three charts that
install in a set order, each waiting for the one before it with `dependsOn`.

Nothing applies this directory directly. A cluster or another stack lists it under `resources:`, and the Flux
Kustomization that applies that directory puts its objects into the organisation's namespace, `org-<name>`. The
`HelmRelease`s install into the workload cluster through its `${cluster_name}-kubeconfig` Secret.

## What's here

Each chart has a directory with an `oci-repository.yaml` (the chart and its version) and a `helm-release.yaml`, and
they all have the same shape:

1. [`gateway-api-crds/`](gateway-api-crds/): the Gateway API CRDs, into `kube-system`.
1. [`envoy-gateway/`](envoy-gateway/): the Envoy Gateway controller, into `envoy-gateway-system`. Waits for the CRDs.
1. [`gateway-api-config/`](gateway-api-config/): the `giantswarm-default` GatewayClass and Gateway. Waits for the
   controller.

Next to them:

- `default_config_gateway_api_crds.yaml`, `default_config_envoy_gateway.yaml`, `default_config_gateway_api_config.yaml`:
  the stack's default values for each chart. The Gateway's comments list what the workload cluster needs first.
- `kustomization.yaml`: lists the six objects and turns the defaults into `${cluster_name}-<chart>-values` ConfigMaps.

`dependsOn` orders installs and upgrades, but not deletes: when a Kustomization prunes the stack, helm-controller
uninstalls all three at once. So `gateway-api-config` sets `spec.uninstall.disableWait`, and its uninstall doesn't
wait for the GatewayClass to go. If Envoy Gateway is gone before it has cleared the GatewayClass's finalizer, the
GatewayClass stays `Terminating`. That only matters when you remove the stack from a workload cluster that stays up.
Clear the finalizer there with:

```sh
kubectl patch gatewayclass giantswarm-default --type=merge -p '{"metadata":{"finalizers":null}}'
```

## When you copy it

List the stack as it is, and give a cluster its own values in `${cluster_name}-<chart>-user-values`, as the out-of-band
examples' `cluster/apps/envoy-gateway-from-template/` do. Keep the release names, the `dependsOn` chain and the
Gateway's name, `giantswarm-default`: apps attach their `HTTPRoute`s to it.

## Read more

- [Stacks tutorial](/docs/tutorials/intermediate/stacks.md)
- [Order it after another release](/docs/tutorials/intermediate/app-templates.md#order-it-after-another-release)
