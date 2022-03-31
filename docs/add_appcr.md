# Add a new App to the Workload Cluster

Follow the below instructions to add a new App to this repository.

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and several App-related values are needed
in multiple places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
export APP_VERSION=APP_VERSION
export APP_CATALOG=APP_CATALOG
export APP_NAMESPACE=APP_NAMESPACE
# OPTIONAL
export APP_USER_VALUES=CONFIGMAP_OR_SECRET_PATH
```

## Directory tree

1. Go to the `apps` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps
    ```

1. Create new directory with a name corresponding to the App name:

    ```sh
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

    **Note**, you can optionally configure App with the user-provided values by adding below flags to the previous command:

    ```sh
    --user-configmap ${APP_USER_VALUES}
    --user-secret ${APP_USER_VALUES}
    ```

    Reference [the App Configuration](https://docs.giantswarm.io/app-platform/app-configuration/) for more details of how
    to properly create respective ConfigMaps or Secrets.

1. (optional) Place ConfigMap and Secrets with values as the `configmap.yaml` and `secret.enc.yaml` files respectively:

    ```sh
    # Use one of the two for respective kind
    cp ${APP_USER_VALUES} ./configmap.yaml
    # cp ${APP_USER_VALUES} ./secret.enc.yaml
    ```

1. (optional) Import the regular GPG public key of the Workload Cluster and encrypt the `secret.enc.yaml` file:

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

At this point, if you have followed [the WC configuration guide](./add_wc.md), all the necessary Flux resources should
already be configured.

Recommended next steps:

- [enable automatic updates of an existing App](./automatic_updates_appcr.md)
- [update an existing App](./update_appcr.md)
