# Add a new App Template to the repository

- [Add a new App Template to the repository](#add-a-new-app-template-to-the-repository)
  - [Example](#example)
  - [Export environment variables](#export-environment-variables)
  - [Setting up directory tree structure for managing apps](#setting-up-directory-tree-structure-for-managing-apps)
  - [Recommended next steps](#recommended-next-steps)

In order to avoid adding the same application from scratch across all your clusters, you can prepare App Templates that provide
a pre-configured version of an App. This also allows you to manage and version an app's config even if the app itself is
not yet installed in any cluster.

## Example

An example of an App Template is available in [bases/apps/nginx-ingress-controller](../../bases/apps/nginx-ingress-controller).

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and several App-related values are needed
in multiple places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
export APP_VERSION=APP_VERSION
export APP_CATALOG=APP_CATALOG
export APP_NAMESPACE=APP_NAMESPACE
# OPTIONAL
export APP_USER_VALUES=CONFIGMAP_OR_SECRET_PATH
```

## Setting up directory tree structure for managing apps

1. Go to the `apps` directory and prepare a directory for the new App Template:

    ```sh
    cd bases/apps/
    mkdir ${APP_NAME}
    ```

1. Go to the newly created directory and use [the kubectl-gs plugin](https://github.com/giantswarm/kubectl-gs) to
generate the [App CR](https://docs.giantswarm.io/ui-api/kubectl-gs/template-app/):

    ```sh
    cd ${APP_NAME}/
    kubectl gs template app \
    --app-name ${APP_NAME} \
    --catalog ${APP_CATALOG} \
    --cluster ${WC_NAME} \
    --name ${APP_NAME} \
    --namespace ${APP_NAMESPACE} \
    --version {$APP_VERSION} > appcr.yaml
    ```

    **Note**, you most likely want to provide a default configuration, so add any of the below flags to the previous command:

    ```sh
    --user-configmap ${APP_USER_VALUES}
    --user-secret ${APP_USER_VALUES}
    ```

    Reference [the App Configuration](https://docs.giantswarm.io/app-platform/app-configuration/) for more details about
    how to properly create the respective ConfigMaps or Secrets.

    If you want to provide a default config, we can use us the ConfigMap generator feature of `kustomize`.
    This allows us to use a pure YAML file for the configuration, without the wrapping into a ConfigMap. Still, for Secrets
    we need to encrypt them as a Secret object and the generator approach won't work. Refer our [adding an App](./add_appcr.md)
    docs to check how to add and encrypt a Secret. For configuration that can be used as a ConfigMap, just add the content
    to a `default_config.yaml` file.

1. Add the `kustomization.yaml` file, adding an optional Secret as a resource and a ConfigMapGenerator for plain text config:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    buildMetadata: [originAnnotations]
    # default config block start - include if you provide default config
    configMapGenerator:
      - files:
        - values=default_config.yaml
        name: ${workload_cluster_name}-nginx-ingress-controller-values
    generatorOptions:
      disableNameSuffixHash: true
    # default config block end
    resources:
      - appcr.yaml
      - secret.enc.yaml # only if you provide default Secret
    ```

At this point, you should have a ready App Template.

## Recommended next steps

- [install an App](add_appcr.md)
- [create an App Set](app_sets.md)
