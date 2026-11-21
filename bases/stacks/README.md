# stacks

`bases/stacks`

Stacks: several apps a cluster installs together, with what ties them together in one place. That's the order they
install in, the values that have to agree with each other, and the chart versions known to work together. A cluster
lists the stack, not each app.

Nothing applies this directory directly. A `kustomization.yaml` in a cluster's directory lists a stack under
`resources:`, and the Flux Kustomization that applies that directory puts the stack's objects into the organisation's
namespace, `org-<name>`. From there the `HelmRelease`s install into the workload cluster.

## What's here

- [`envoy-gateway/`](envoy-gateway/): Envoy Gateway, as three charts installed in order.
- [`hello-web/`](hello-web/): a stack of a stack and an app, hello-world served over HTTPS through Envoy Gateway.

## When you copy it

Copy a stack to a directory named after yours. Keep its apps' `${cluster_name}-<chart>` names: the `dependsOn` and the
patches find the releases by name. A stack can replace its apps' `-values` ConfigMaps, as `hello-web` does, so a
cluster's own overrides go into the `-user-values` ConfigMaps and `-user-secrets` Secrets.

## Read more

- [Stacks tutorial](/docs/tutorials/intermediate/stacks.md)
- [Bases, Components and stacks](/docs/explanation/composition.md#bases-components-and-stacks)
