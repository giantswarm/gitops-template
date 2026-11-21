# bases/apps

App Templates: one app's chart, version and default values, written once and installed on any number of workload
clusters. Each directory here is one App Template, and they all have the same shape, so this README covers them.

Nothing applies this directory directly. A `kustomization.yaml` in a cluster's directory, or a stack, lists an App
Template under `resources:`, and the Flux Kustomization that applies that cluster directory puts it into the
organisation's namespace, `org-<name>`, with `${cluster_name}` set to that cluster.

## What's here

[`hello-world/`](hello-world/) is the example:

- `oci-repository.yaml`: where the chart comes from, and the version in `spec.ref.tag`.
- `helm-release.yaml`: installs the chart into the workload cluster through its `${cluster_name}-kubeconfig` Secret.
- `default_config.yaml`: the App Template's default values, which `kustomization.yaml` turns into the
  `${cluster_name}-hello-world-values` ConfigMap.
- `kustomization.yaml`: lists the two objects and generates the values ConfigMap.

The `HelmRelease` reads its values in layers, and later ones win: the cluster's values, then the App Template's
defaults, then the optional `-user-values` ConfigMap and `-user-secrets` Secret that a cluster adds for its own
overrides.

hello-world's `HTTPRoute` needs the Gateway API CRDs, but the App Template leaves that `dependsOn` out on purpose: a
`HelmRelease` that `dependsOn` names has to exist, so the App Template would only work next to Envoy Gateway. The
layer that installs both together, such as [`bases/stacks/hello-web`](../stacks/hello-web/), adds the dependency.

## When you copy it

Copy `hello-world/` to a directory named after your app, then change the chart `url`, the version, `releaseName`,
the target and storage namespaces, and the defaults. Keep the `${cluster_name}-<app>` names and the four
`valuesFrom` layers in that order: the clusters' overrides rely on both.

## Read more

- [App Templates tutorial](/docs/tutorials/intermediate/app-templates.md)
- [App values](/docs/reference/values.md#app-values)
