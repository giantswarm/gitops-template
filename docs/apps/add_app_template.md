# Add a new App Template to the repository

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Setting up directory tree structure for managing apps](#setting-up-directory-tree-structure-for-managing-apps)
- [Recommended next steps](#recommended-next-steps)

In order to avoid adding the same application from scratch across all your clusters, you can prepare App Templates that provide
a pre-configured version of an App. This also allows you to manage and version an app's config even if the app itself is
not yet installed in any cluster.

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

1. Go to the `apps` directory and prepare a directory for the new App Template:

    ```sh
    cd bases/apps/
    mkdir ${APP_NAME}
    cd ${APP_NAME}/
    ```

1. Create the `OCIRepository` that points at the chart:

    ```sh
    cat <<EOF > ocirepository.yaml
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
    cat <<EOF > helmrelease.yaml
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
       overrides for a single cluster, see [adding an App](./add_appcr.md).

1. Put the default configuration of the app, plain Helm values, into the `default_config.yaml` file. We use the
   ConfigMap generator feature of `kustomize` to turn it into the `${cluster_name}-${APP_NAME}-values` ConfigMap, so the
   file doesn't need to be wrapped into a ConfigMap:

    ```sh
    cat <<EOF > default_config.yaml
    # default values of the ${APP_CHART} chart
    EOF
    ```

    Values that have to be kept secret don't belong here: provide them per cluster through the `-user-secrets`
    Secret, see [adding an App](./add_appcr.md).

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
    kind: Kustomization
    resources:
      - helmrelease.yaml
      - ocirepository.yaml
    EOF
    ```

At this point, you should have a ready App Template.

## Recommended next steps

- [Add a new App to a Workload Cluster](add_appcr.md)
- [Creating and using App Sets](app_sets.md)
