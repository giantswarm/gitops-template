# Deploy several apps together as a stack

- [Example](#example)
- [When a stack helps](#when-a-stack-helps)
- [Creating a stack](#creating-a-stack)
- [Using a stack in a cluster](#using-a-stack-in-a-cluster)
- [Limits](#limits)
- [A base or a Component](#a-base-or-a-component)
- [Recommended next steps](#recommended-next-steps)

A stack is several `HelmRelease`s that are deployed together and may depend on each other. It's a kustomize base: a
directory with a `kustomization.yaml` that kustomize builds into a list of objects. Its `resources:` lists the
[App Templates](./app-templates.md) of its apps, which can each still be used on their own, and the stack adds what
ties them together. Stacks live in `bases/stacks`. A cluster lists a stack in its apps like an App Template, and gets
all of its apps.

## Example

[hello-web](/bases/stacks/hello-web/) installs [hello-world](/bases/apps/hello-world/), served over HTTPS through
[Envoy Gateway](/bases/apps/envoy-gateway/). It lists both App Templates and adds what makes hello-world reachable
through the Gateway:

```text
bases/stacks/hello-web
├── kustomization.yaml       resources: the envoy-gateway and hello-world App Templates, the dependsOn and version patches
├── gateway_api_config.yaml  the Gateway, with the `hello` subdomain
└── hello_world.yaml         hello-world, with the hostname `hello.<base domain>` on that Gateway
```

## When a stack helps

Put apps into a stack when they are deployed together and some of these apply:

- **Order.** One app needs another to be installed first. The stack adds the `dependsOn` once, instead of every
  cluster adding it, see [App Templates](./app-templates.md) for how `dependsOn` works.
- **Values that have to agree.** One app's values have to match another's. In hello-web, the Gateway's
  `listeners.https.subdomains` lists `hello`, and hello-world's `route.hostnames` is `hello.{{ .Values.baseDomain }}`
  on the Gateway in `route.parentRefs`. Both files are in the same directory, so a change to one is seen next to the
  other.
- **Versions known to work together.** The stack pins the chart version of each app in its `kustomization.yaml`, with
  a `# renovate:` comment, so the versions that are tested together are in one place and Renovate updates them in one
  pull request.
- **One line per cluster.** Adding `hello-web` to a cluster's apps adds the whole stack, and removing it removes the
  whole stack.

If the apps are independent, don't make a stack: list each App Template in the cluster.

## Creating a stack

1. Create a directory for it under `bases/stacks`.

1. Put the values each app gets into a file of its own. Each file replaces the App Template's whole `-values`
   ConfigMap, so it has to hold every default the app needs: start from the App Template's default config and change
   what the stack needs. The `-user-values` ConfigMaps and `-user-secrets` Secrets stay free for a cluster's own
   values.

1. Write the `kustomization.yaml`. In hello-web it looks like this, shortened to the version patch of hello-world:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - behavior: replace
        files:
          - values=gateway_api_config.yaml
        name: ${cluster_name}-gateway-api-config-values
      - behavior: replace
        files:
          - values=hello_world.yaml
        name: ${cluster_name}-hello-world-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    namespace: org-${organization}
    patches:
      - patch: |-
          - op: add
            path: /spec/dependsOn
            value:
              - name: ${cluster_name}-gateway-api-crds
        target:
          kind: HelmRelease
          name: \${cluster_name}-hello-world
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
            value: "3.2.2"
        target:
          kind: OCIRepository
          name: \${cluster_name}-hello-world
    resources:
      - ../../apps/envoy-gateway
      - ../../apps/hello-world
    ```

    The `name` of each generated ConfigMap has to be the name the listed App Template uses, and `namespace` the
    organisation's namespace, or `behavior: replace` finds nothing to replace. The `$` of a target name is escaped,
    as `kustomize` reads the name as a regular expression. A label under `labels:` marks every object the stack
    builds, if you want to find them on the management cluster later; it is a plain label that nothing acts on.

## Using a stack in a cluster

Use it as you use an [App Template](./add-app.md#adding-app-using-app-template): a directory in the cluster's `apps`,
whose `kustomization.yaml` lists the stack under `resources:`. A cluster template lists it in its
`apps/kustomization.yaml`, as [hello_app_cluster](/bases/cluster_templates/hello_app_cluster/apps/) does. There is no
`${cluster_name}-hello-web` `HelmRelease`: to change an app's values for one cluster, add a `configMapGenerator` entry
named after that app, `${cluster_name}-<app>-user-values`, as
[apps/hello-world-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-from-template/)
does for hello-world.

A stack and an App made from one of the App Templates it lists produce objects with the same names, for example
`${cluster_name}-hello-world`. A cluster can only have one of them. To move an app into a stack, or out of it, change
both in the same commit: the objects keep their names, so Flux updates them in place instead of reinstalling the app.

The out-of-band example clusters install Envoy Gateway as a base app, with the cluster, and hello-world from its own
App Template as a secondary app, once the cluster is ready. A stack's apps are always applied by the same
Kustomization, so when some of them have to be base apps, list the App Templates separately, as those clusters do.

## Limits

kustomize is not a templating engine. It can replace values, but it can't set one value in several places, so values
that have to agree are written in each app's file, as hello-web does with the `hello` subdomain. Two apps can only
share values by listing the same ConfigMap or Secret in `valuesFrom`, and then both charts have to understand every key
in it the same way.

When that isn't enough, two other ways fit better:

- an umbrella Helm chart, which installs the apps as
  [sub-charts](https://helm.sh/docs/chart_template_guide/subcharts_and_globals/) and can pass one value to all of them;
- a Flux Operator `ResourceSet` in the organisation's `multicluster/apps`, which renders the apps for several clusters
  from one set of inputs, see [Apps on several clusters](./scheduled-updates.md#apps-on-several-clusters).

## A base or a Component

Make a stack a base, under `resources:`, as hello-web is. Use a
[kustomize Component](https://kubectl.docs.kubernetes.io/guides/config_management/components/) only when the piece has
to patch objects outside itself, in an order that matters, as the [regions](./environments.md#regions) do when they
append to the cluster's `valuesFrom`. A stack only adds objects. A base also builds on its own, so it can be the path
of a Flux `Kustomization`, and a Component can't.

## Recommended next steps

- [Add a new App Template to the repository](./app-templates.md)
- [Add Workload Cluster environments](./environments.md), which install hello-web through a cluster template
