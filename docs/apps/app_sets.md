# Creating and using App Sets

- [Limitations](#limitations)
- [Example](#example)
  - [App Set Template](#app-set-template)
  - [Using App Set](#using-app-set)
- [Creating an App Set Template](#creating-an-app-set-template)
- [Using an App Set](#using-an-app-set)

It is often desireable to deploy a group of apps together, as a single deployment step. We call such groups "App Sets".
There's nothing special about App Sets: they are not a separate API entity, rather just a configuration pattern
enabled by `kustomize` and `flux`. The purpose of such approach can vary, but it's usually to meet the following benefits:

- Apps within the set have strong relationship and dependency on versions and you want to be sure that the correct
  versions are used and deployed together.
- Configuration of one app in a set depends on configuration of another app in the same set. By placing them together it
  is possible to simplify configuration of one app by providing values known to depend on another. As a result, it is
  easier to deploy an App Set than each of the apps individually. That way a specialized team might deliver a
  pre-configured App Set so that it is easy and understandable to deploy be a less proficient end user.

## Limitations

Even though App Sets have a lot of benefits, their implementation with `kustomize` and `flux` is pretty limited.
Please make sure that you read this section before deciding to implement App Sets the way they are described here.

In general, the whole problem can be summarized as "`kustomize` is not a templating engine". It can override some values,
even in bulks, but it can't put the same value in any arbitrary place.

In general case, it is impossible to configure a variable once and use it with multiple apps. There are only 2 choices
here: either each pair of apps lists exactly the same ConfigMap/Secret in the `valuesFrom` of their `HelmRelease`s or
they use two separate ConfigMaps. In the latter case, it is your responsibility to provide exactly the same value in
both ConfigMaps/Secrets. In the former, it means that your apps share the same configuration input and must be able to
handle this situation correctly: there can be no conflicting options and each shared option must be understood exactly
the same by each app. In practice, it means that the apps must be prepared on Helm chart layer to work together.
If none of these two solutions is applicable, you might want to solve the problem of bundling the apps together
elsewhere. One of possible routes is to create a new umbrella Helm Chart that includes all the necessary apps
as [sub-charts](https://helm.sh/docs/chart_template_guide/subcharts_and_globals/).

## Example

### App Set Template

An example of an App Set Template is available in [bases/app_sets/hello-web-app](/bases/app_sets/hello-web-app/).
This App Set assumes, that it's impossible to build a shared ConfigMap for its Apps and as such does full config
override on App Set template level and overrides single values with the apps' `-user-values` ConfigMaps in the App Set
instance.

The shipped example currently bundles a single app, `hello-world`. The mechanics below are identical for any number
of apps: list each App Template under `resources:` and give each its own config and version override.

### Using App Set

An example showing how to use an App Set is available in
[WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/app_sets/hello-web-app-1](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/app_sets/hello-web-app-1).

## Creating an App Set Template

Creating an App Set Template is not much different than [creating an App Template](add_app_template.md). Please check the
docs there first, if you haven't already. The steps below create the `hello-web-app` example, which bundles the
`hello-world` App Template; replace the names with your own.

1. From the root of the repository, create a directory for the App Set Template under `bases/app_sets`, and enter it:

    ```sh
    mkdir -p bases/app_sets/hello-web-app
    cd bases/app_sets/hello-web-app
    ```

1. (optional - if replacing the default config of an app in the set) Put the values the app gets in this set into a
   file. It replaces the App Template's whole `-values` ConfigMap, so it has to hold every default the app needs:

    ```sh
    cat <<'EOF' > default_config_hello_world.yaml
    replicaCount: 2
    EOF
    ```

1. Create the `kustomization.yaml`. The quoted `'EOF'` keeps the shell from expanding `${cluster_name}` and
   `${organization}`, which Flux substitutes later:

    ```sh
    cat <<'EOF' > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    labels:
      - pairs:
          gitops.giantswarm.io/appSet: hello-web-app # this label will be applied to all resources included in the App Set
    # (optional) replace default config of apps included in the set
    configMapGenerator:
      - behavior: replace
        files:
        - values=default_config_hello_world.yaml
        name: ${cluster_name}-hello-world-values # has to be in sync with the name used by included app
    # block end
    kind: Kustomization
    namespace: org-${organization} # the org namespace: the kubeconfig Secret, cluster values and OCIRepositories live there
    # (optional) here we can enforce versions of the apps that we know work well together
    patches:
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            value: "3.2.2"
        target:
          kind: OCIRepository
          name: \${cluster_name}-hello-world
    # block end
    resources:
      - ../../apps/hello-world
    EOF
    ```

Please note the following in the example above:

- We use the `gitops.giantswarm.io/appSet: YOUR_NAME` label to identify all the components included in the App Set.
  It is a plain label, nothing acts on it, but it makes debugging easier later, as you can easily find what belongs
  to the Set after it is deployed:

  ```sh
  kubectl get helmreleases,ocirepositories,configmaps -n org-${ORG_NAME} -l gitops.giantswarm.io/appSet=YOUR_NAME
  ```

  The label is set on the objects the App Set Template builds, on the Management Cluster. Objects added by an App Set
  instance, like its `-user-values` ConfigMap, don't get it, and neither do the resources the charts install in the
  Workload Cluster. `labels` only labels the objects' metadata; unlike the deprecated `commonLabels`, it leaves
  selectors alone.
- One of the key benefits of App Sets is to be able to provide a specific set of app versions, that is known to make
  the apps work well together. Over here, we do that as a set of in-line patches, so it is immediately visible
  in the `kustomization.yaml` file which versions are used.
- Each `HelmRelease` reads its values in layers: the cluster values, the app's `-values` ConfigMap, then the
  optional `-user-values` ConfigMap and `-user-secrets` Secret. Since we always want to leave the user layers at the
  end users disposal, we're left with overriding the whole `-values` ConfigMap coming from the base application as
  the only option.
- It is recommended to re-use App Templates to create App Set Templates. That's exactly what we do here: apps defined
  in the `resources:` block are App Templates, that, if needed, can be also used standalone.
- The example above doesn't cover handling Secrets - we do that for brevity. Secrets can be created the same way as in
  normal [App Templates](./add_app_template.md) and overrode the same as ConfigMaps or Secrets when creating
  [App from a Template](./add_appcr.md#adding-app-using-app-template).

## Using an App Set

Using an App Set Template is once again very similar to using a single
[App Template](./add_appcr.md#adding-app-using-app-template).

**Note**, an App Set and a standalone App created from the same App Template produce objects with the same names, for
example `${cluster_name}-hello-world`. A cluster can only have one of them. To move an app that is installed
standalone into a set, remove it from the `mapi/apps` directory in the same commit that adds the set: the objects keep
their names, so Flux updates them in place instead of reinstalling the app.

1. Export the names of the Management Cluster, Organization and Workload Cluster:

    ```sh
    export MC_NAME=CODENAME
    export ORG_NAME=ORGANIZATION
    export WC_NAME=CLUSTER_NAME
    ```

1. Create a directory for the App Set in the `mapi/app_sets` directory of your Workload Cluster, and enter it:

    ```sh
    mkdir -p management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/app_sets/hello-web-app-1
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/app_sets/hello-web-app-1
    ```

1. (optional - if overriding the config of an app in the set) Put only the values to change into a file:

    ```sh
    cat <<'EOF' > override_config_hello_world.yaml
    replicaCount: 3
    EOF
    ```

1. Create the `kustomization.yaml`, pointing at the App Set Template from the
   [bases/app_sets](/bases/app_sets/) directory:

    ```sh
    cat <<'EOF' > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
          - values=override_config_hello_world.yaml
        name: ${cluster_name}-hello-world-user-values
    generatorOptions:
      disableNameSuffixHash: true
    kind: Kustomization
    namespace: org-${organization}
    resources:
      - ../../../../../../../../../bases/app_sets/hello-web-app
    EOF
    ```

    There is no list to update: the `mapi` directory has no `kustomization.yaml`, so Flux picks up every directory
    with a `kustomization.yaml` below it, including the new one.

Over here, we are overriding the configuration of the `hello-world` app, which was already defined in the App Set
Template. The `${cluster_name}-hello-world-user-values` ConfigMap is the optional user layer the app's `HelmRelease`
already lists in `spec.valuesFrom`, so creating it is enough: no patch is needed, and we don't have to override the
whole config, but only YAML keys we need to change. The namespace has to stay the organization namespace, as the
`HelmRelease` finds its kubeconfig Secret, cluster values and `OCIRepository` there; the namespace the app is
installed into on the workload cluster is its `spec.targetNamespace`. If you want to learn more about how config
overrides work, please consult our [docs about creating apps](add_appcr.md), as in general App Set is just a bundle of them.
