# Add a new App to a Workload Cluster

- [Add a new App to a Workload Cluster](#add-a-new-app-to-a-workload-cluster)
  - [Examples](#examples)
  - [Common steps](#common-steps)
    - [Export environment variables](#export-environment-variables)
    - [Setting up directory tree structure for managing apps](#setting-up-directory-tree-structure-for-managing-apps)
  - [Adding App directly](#adding-app-directly)
  - [Adding App using App Template](#adding-app-using-app-template)
  - [Recommended next steps](#recommended-next-steps)

Follow the instructions below to add a new App to a cluster managed in this repository.
You can add an App directly (without any intermediate step) or use an [App Template](add_app_template.md).
The documentation below shows common steps as well as what is different in both cases.

## Examples

Examples of creating apps are available in following locations:

- An example of a directly configured App (the simplest use case - no configuration): an [app without configuration](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/apps/hello-world/)
- An example of a directly configured App (with configuration): an [app that uses a configuration ConfigMap](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/apps/nginx-ingress-controller/)
- An example of an App created from App Template is available in [WC_NAME/apps/nginx-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/apps/nginx-from-template/).

## Common steps

Please follow these steps when installing an App directly as well as using App Template.

### Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and several App-related values are needed
in multiple places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME="\${WC_NAME}-APP_NAME"
```

### Setting up directory tree structure for managing apps

1. Go to the `apps` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps
    ```

1. Create new directory with a name corresponding to the App name:

    ```sh
    mkdir ${APP_NAME}
    ```

## Adding App directly

1. Set remaining env variables

    ```sh
    export APP_VERSION=APP_VERSION
    export APP_CATALOG=APP_CATALOG
    export APP_NAMESPACE=APP_NAMESPACE
    # OPTIONAL
    export APP_USER_VALUES=CONFIGMAP_OR_SECRET_PATH
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

    **Note**, you can optionally configure App with the user-provided values by adding below flags to the previous command:

    ```sh
    --user-configmap ${APP_USER_VALUES}
    --user-secret ${APP_USER_VALUES}
    ```

    **Note**, We're including `${cluster_id}` in the app name to avoid a problem when two
    or more clusters in the same organization want to deploy the same app with its
    default name.

    Reference [the App Configuration](https://docs.giantswarm.io/app-platform/app-configuration/) for more details of how
    to properly create respective ConfigMaps or Secrets.

1. (optional - if adding configuration) Place ConfigMap and Secrets with values as the `configmap.yaml`
  and `secret.enc.yaml` files respectively:

    ```sh
    # Use one of the two for respective kind
    cp ${APP_USER_VALUES} ./configmap.yaml
    # cp ${APP_USER_VALUES} ./secret.enc.yaml
    ```

1. (optional - if encrypting secrets) Import the regular GPG public key of the Workload Cluster and encrypt
  the `secret.enc.yaml` file:

    ```sh
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc
    sops --encrypt --in-place secret.enc.yaml
    ```

1. Go back to the `apps` directory:

    ```sh
    cd ..
    ```

1. Edit the `kustomization.yaml` there adding all the newly created files as resources:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${APP_NAME}/appcr.yaml
    - ${APP_NAME}/secret.enc.yaml
    - ${APP_NAME}/configmap.yaml
    ```

  At this point, if you have followed [the WC configuration guide](../add_wc.md), all the necessary Flux resources should
  already be configured.

## Adding App using App Template

1. First, you need to pick a directory with an App Template from the [`bases/apps`](/bases/apps/) dir. Export the
path to the directory in an env variable:

    ```sh
    export APP_TEMPLATE_DIR=[YOUR_BASE_PATH]
    ```

    Make sure your `APP_NAME` variable is set to the exact same name as used for the app in the App Template you're
    pointing to.

1. In the current directory
    (`management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}`)
    create a new `kustomization.yaml` with the following content:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    # configuration override block start - include only if overriding default config from the Template
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: ${WC_NAME}-${APP_NAME}-user-values
    generatorOptions:
      disableNameSuffixHash: true
    # configuration override block end
    kind: Kustomization
    patchesStrategicMerge:
      - config_patch.yaml
    resources:
      - ../../../../../../../../${APP_TEMPLATE_PATH}
      - secret.enc.yaml # only if including a secret
    ```

    Please note, that the block marked "configuration override block" is needed only if you override the default (from the
    Template) config and the `- secret.enc.yaml` only if you override the secret. If you don't override any, skip both
    parts in `kustomization.yaml` and also skip next three configuration points below.

1. (optional - if you override either config or secret) Create a patch configuration file, that will enhance your App
    Template with a `userConfig` attribute (refer to
    [the App Configuration](https://docs.giantswarm.io/app-platform/app-configuration/) for more details about how `config`
    and `userConfig` properties of App CR are used).

    ```sh
    cat <<EOF > config_patch.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: ${WC_NAME}-${APP_NAME}
    spec:
      userConfig:
        configMap: # include if you override the config from Template
          name: ${WC_NAME}-${APP_NAME}-user-values
        secret: # include if you override the secret from Template
          name: ${WC_NAME}-${APP_NAME}-user-secret
    ```

1. (optional - if you override config) Create a YAML file `override_config.yaml` containing the App configuration you
  want to override in comparison to App Template.

1. (optional - if you override secret) Create a `sops` encrypted secret as [explained above](#adding-app-directly).
   Make sure that the Secret name is `${WC_NAME}-${APP_NAME}-user-secret`. Then, append the following to the
   `spec.userConfig` section of file `config_patch.yaml`:

   ```yaml
   secret:
     name: ${WC_NAME}-${APP_NAME}-user-secret
   ```

   Also, add the line below to the `resources:` section of the `kustomization.yaml` file:

   ```yaml
   - secret.enc.yaml
   ```

1. Additional notes

    If you want to, you can use the same idea of App Templates to override any property (like app version) of base
    App Template by using
    [kustomize patches](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/patches/).

1. Everything is ready, commit the changes to the branch your Flux is using.

## Recommended next steps

- [Enable automatic updates of an existing App](./automatic_updates_appcr.md)
- [Update an existing App](./update_appcr.md)
