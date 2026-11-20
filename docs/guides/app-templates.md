# Add a new App Template to the repository

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Setting up directory tree structure for managing apps](#setting-up-directory-tree-structure-for-managing-apps)
- [App Templates with several apps](#app-templates-with-several-apps)
  - [When grouping helps](#when-grouping-helps)
  - [Creating one](#creating-one)
  - [Using one in a cluster](#using-one-in-a-cluster)
  - [Limits](#limits)
  - [A base or a Component](#a-base-or-a-component)
- [Recommended next steps](#recommended-next-steps)

In order to avoid adding the same application from scratch across all your clusters, you can prepare App Templates that
provide a pre-configured version of an App. This also allows you to manage and version an app's config even if the app
itself is not yet installed in any cluster.

An app is a Flux `HelmRelease` that installs a Helm chart into the workload cluster, and an `OCIRepository` that
points at the chart in an OCI registry. Both live in the organization namespace on the management cluster.

## Example

An example of an App Template is available in [bases/apps/hello-world](/bases/apps/hello-world).

## Export environment variables

**Note**, several App-related values are needed in multiple places across this instruction, the least error prone way
of providing them is by exporting as environment variables:

```sh
export APP_NAME=APP_NAME            # name of the app, used in resource names and as the Helm release name
export APP_CHART=APP_CHART          # name of the chart in the registry, for example `hello-world`
export APP_VERSION=APP_VERSION      # chart version (OCI tag), for example `3.2.2`
export APP_NAMESPACE=APP_NAMESPACE  # namespace in the workload cluster the app is installed into
```

The examples below use the Giant Swarm catalog, whose charts are published under
`oci://gsoci.azurecr.io/charts/giantswarm`. Change the `url` of the `OCIRepository` to use a chart from another
registry.

## Setting up directory tree structure for managing apps

1. From the root of the repository, create a directory for the new App Template under `bases/apps`, which is
   created too if this is the first App Template, and enter it:

    ```sh
    mkdir -p bases/apps/${APP_NAME}
    cd bases/apps/${APP_NAME}/
    ```

1. Create the `OCIRepository` that points at the chart:

    ```sh
    cat <<EOF > oci-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        tag: ${APP_VERSION}
      url: oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART}
    EOF
    ```

1. Create the `HelmRelease` that installs the chart into the workload cluster:

    ```sh
    cat <<EOF > helm-release.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: \${cluster_name}-${APP_NAME}
        namespace: org-\${organization}
      install:
        createNamespace: true
        remediation:
          remediateLastFailure: false
          retries: 10
      interval: 5m
      kubeConfig:
        secretRef:
          name: \${cluster_name}-kubeconfig
      releaseName: ${APP_NAME}
      storageNamespace: ${APP_NAMESPACE}
      targetNamespace: ${APP_NAMESPACE}
      timeout: 10m
      upgrade:
        remediation:
          remediateLastFailure: true
          retries: 10
          strategy: rollback
      valuesFrom:
        - kind: ConfigMap
          name: \${cluster_name}-cluster-values
          valuesKey: values
        - kind: ConfigMap
          name: \${cluster_name}-${APP_NAME}-values
          valuesKey: values
        - kind: ConfigMap
          name: \${cluster_name}-${APP_NAME}-user-values
          optional: true
          valuesKey: values
        - kind: Secret
          name: \${cluster_name}-${APP_NAME}-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

    **Note**, we're including `${cluster_name}` in the resource names to avoid a problem when two
    or more clusters in the same organization want to deploy the same app.

    The `kubeConfig` points the release at the workload cluster. Flux merges the `valuesFrom` entries in order, later
    entries win:

    1. `${cluster_name}-cluster-values`, created for every workload cluster with values like `baseDomain`,
    1. `${cluster_name}-${APP_NAME}-values`, the default configuration of this App Template,
    1. `${cluster_name}-${APP_NAME}-user-values` and `${cluster_name}-${APP_NAME}-user-secrets`, optional
       overrides for a single cluster, see [adding an App](./add-app.md).

1. Put the default configuration of the app, plain Helm values, into the `default_config.yaml` file. We use the
   ConfigMap generator feature of `kustomize` to turn it into the `${cluster_name}-${APP_NAME}-values` ConfigMap, so the
   file doesn't need to be wrapped into a ConfigMap:

    ```sh
    cat <<EOF > default_config.yaml
    # default values of the ${APP_CHART} chart
    EOF
    ```

    Values that have to be kept secret don't belong here: provide them per cluster through the `-user-secrets`
    Secret, see [adding an App](./add-app.md).

1. Add the `kustomization.yaml` file:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
        - values=default_config.yaml
        name: \${cluster_name}-${APP_NAME}-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    resources:
      - helm-release.yaml
      - oci-repository.yaml
    EOF
    ```

At this point, you should have a ready App Template.

An App Template that installs several charts, like [envoy-gateway](/bases/apps/envoy-gateway/), gives each chart a
directory of its own with a `helm-release.yaml` and an `oci-repository.yaml`, and lists all of them in one
`kustomization.yaml`. Every file then holds a single resource, as the files `kubectl gs gitops` writes do, so commands
like `yq -i '.spec.ref.tag = "NEW_VERSION"' oci-repository.yaml` change only the chart you mean.

When a chart needs something another `HelmRelease` installs first, such as its CRDs, list that `HelmRelease` in
`dependsOn`. helm-controller checks `dependsOn` on every reconciliation, so every install and upgrade of the chart
waits until the other release is `Ready`, and the install retries can stay bounded, so a broken install still fails.
A `HelmRelease` that `dependsOn` names has to exist, or the release waits forever. So an App Template that can be
used on its own leaves the dependency out, and the layer that installs it together with the other App Template adds
it. [hello-world](/bases/apps/hello-world/helm-release.yaml) is an example: its `HTTPRoute` needs the Gateway API CRDs
that the envoy-gateway App Template installs, and the [hello-web](/bases/apps/hello-web/) App Template, which installs
both, adds the dependency with a patch:

```yaml
patches:
  - patch: |-
      - op: add
        path: /spec/dependsOn
        value:
          - name: ${cluster_name}-gateway-api-crds
    target:
      kind: HelmRelease
      name: \${cluster_name}-hello-world
```

The `$` of the target name is escaped, as `kustomize` reads the name as a regular expression.

`dependsOn` doesn't order deletes: when a Kustomization prunes the `HelmRelease`s of an App Template, helm-controller
uninstalls them all at once. In the envoy-gateway App Template, the `gateway-api-config` release therefore sets
`spec.uninstall.disableWait`, so its uninstall doesn't wait for the `giantswarm-default` `GatewayClass` to go. If
Envoy Gateway is removed before it has cleared the `GatewayClass`'s finalizer, the `GatewayClass` stays `Terminating`.
That only matters when you remove the stack from a workload cluster that stays up. Clear the finalizer there with:

```sh
kubectl patch gatewayclass giantswarm-default --type=merge -p '{"metadata":{"finalizers":null}}'
```

## App Templates with several apps

An App Template is a kustomize base: a directory with a `kustomization.yaml` that kustomize builds into a list of
objects. Its `resources:` can list files and other bases, so an App Template can install several apps by listing
several charts, or by listing other App Templates. A cluster lists it in its apps like any other App Template, and gets
all of its apps.

[envoy-gateway](/bases/apps/envoy-gateway/) installs three charts that only make sense together. [hello-web](
/bases/apps/hello-web/) goes one step further: it lists the envoy-gateway and [hello-world](/bases/apps/hello-world/)
App Templates, which can each be used on their own, and adds what makes hello-world reachable over HTTPS through the
Gateway:

```text
bases/apps/hello-web
├── kustomization.yaml       resources: ../envoy-gateway and ../hello-world, the dependsOn and version patches
├── gateway_api_config.yaml  the Gateway, with the `hello` subdomain
└── hello_world.yaml         hello-world, with the hostname `hello.<base domain>` on that Gateway
```

### When grouping helps

Put apps into one App Template when they are deployed together and some of these apply:

- **Order.** One app needs another to be installed first. The App Template adds the `dependsOn`, see above, once,
  instead of every cluster adding it.
- **Values that have to agree.** One app's values have to match another's. In hello-web, the Gateway's
  `listeners.https.subdomains` lists `hello`, and hello-world's `route.hostnames` is `hello.{{ .Values.baseDomain }}`
  on the Gateway in `route.parentRefs`. Both files are in the same directory, so a change to one is seen next to the
  other.
- **Versions known to work together.** The App Template pins the chart version of each app in its `kustomization.yaml`,
  with a `# renovate:` comment, so the versions that are tested together are in one place and Renovate updates them
  in one pull request.
- **One line per cluster.** Adding `hello-web` to a cluster's apps adds the whole stack, and removing it removes the
  whole stack.

If the apps are independent, keep them as separate App Templates and list each in the cluster.

### Creating one

1. Create a directory for it under `bases/apps`, next to the App Templates it lists.

1. Put the values each app gets into a file of its own. Each file replaces the App Template's whole `-values`
   ConfigMap, so it has to hold every default the app needs: start from the App Template's default config and change
   what the group needs. The `-user-values` ConfigMaps and `-user-secrets` Secrets stay free for a cluster's own
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
      - ../envoy-gateway
      - ../hello-world
    ```

    The `name` of each generated ConfigMap has to be the name the listed App Template uses, and `namespace` the
    organisation's namespace, or `behavior: replace` finds nothing to replace. A label under `labels:` marks every
    object the App Template builds, if you want to find them on the management cluster later; it is a plain label that
    nothing acts on.

### Using one in a cluster

Use it as you use any [App Template](./add-app.md#adding-app-using-app-template): a directory in the cluster's
`apps`, whose `kustomization.yaml` lists the App Template under `resources:`. A cluster template lists it in its
`apps/kustomization.yaml`, as [hello_app_cluster](/bases/cluster_templates/hello_app_cluster/apps/) does. There is no
`${cluster_name}-hello-web` `HelmRelease`: to change an app's values for one cluster, add a `configMapGenerator` entry
named after that app, `${cluster_name}-<app>-user-values`, as
[apps/hello-world-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-from-template/)
does for hello-world.

An App Template with several apps and an App made from one of the App Templates it lists produce objects with the same
names, for example `${cluster_name}-hello-world`. A cluster can only have one of them. To move an app into a group, or
out of it, change both in the same commit: the objects keep their names, so Flux updates them in place instead of
reinstalling the app.

The out-of-band example clusters install Envoy Gateway as a base app, with the cluster, and hello-world from its own
App Template as a secondary app, once the cluster is ready. A group's apps are always applied by the same
Kustomization, so when some of them have to be base apps, list the App Templates separately, as those clusters do.

### Limits

kustomize is not a templating engine. It can replace values, but it can't set one value in several places, so values
that have to agree are written in each app's file, as hello-web does with the `hello` subdomain. Two apps can only
share values by listing the same ConfigMap or Secret in `valuesFrom`, and then both charts have to understand every key
in it the same way.

When that isn't enough, two other ways fit better:

- an umbrella Helm chart, which installs the apps as
  [sub-charts](https://helm.sh/docs/chart_template_guide/subcharts_and_globals/) and can pass one value to all of them;
- a Flux Operator `ResourceSet` in the organisation's `multicluster/apps`, which renders the apps for several clusters
  from one set of inputs, see [Apps on several clusters](./scheduled-updates.md#apps-on-several-clusters).

### A base or a Component

Make a group a base, under `resources:`, as hello-web is. Use a
[kustomize Component](https://kubectl.docs.kubernetes.io/guides/config_management/components/) only when the piece has
to patch objects outside itself, in an order that matters, as the [regions](./environments.md#regions) do when they
append to the cluster's `valuesFrom`. A group only adds objects. A base also builds on its own, so it can be the path
of a Flux `Kustomization`, and a Component can't.

## Recommended next steps

- [Add a new App to a Workload Cluster](./add-app.md)
- [Add Workload Cluster environments](./environments.md), which install hello-web through a cluster template
