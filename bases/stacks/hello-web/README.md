# bases/stacks/hello-web

hello-world served over HTTPS through Envoy Gateway: a stack built from the [`envoy-gateway`](../envoy-gateway/) stack
and the [`hello-world`](../../apps/hello-world/) App Template. It holds what ties the two together, so a cluster lists
`hello-web` and gets the lot.

Nothing applies this directory directly. The stage and region examples, `HELLO_APP_*`, list it in their
`cluster/apps/`, and each cluster's Flux Kustomization applies it into the organisation's namespace, `org-<name>`.

## What's here

- `kustomization.yaml`: lists the two bases, makes hello-world wait for the Gateway API CRDs (`dependsOn`), and pins
  the four chart versions that work together.
- `gateway_api_config.yaml`: the Gateway's values, with the `hello` subdomain.
- `hello_world.yaml`: hello-world's values, with its hostname and the Gateway it attaches to.

The two values files replace the bases' `-values` ConfigMaps, and they have to agree: hello-world's hostname,
`hello.<base domain>`, must be one of the Gateway's subdomains, and its `parentRefs` must name the Gateway,
`giantswarm-default`. Keeping them side by side is the point.

## When you copy it

Change the app, its subdomain and hostname together. A stack that replaces a `-values` ConfigMap holds every default
the chart needs, not only the changes. Keep the `# renovate:` comment above each pinned version.

## Read more

- [Stacks tutorial](/docs/tutorials/intermediate/stacks.md#create-a-stack)
- [Stages and regions tutorial](/docs/tutorials/intermediate/stages-and-regions.md)
