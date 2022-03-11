# Add a new App to the Workload Cluster

Follow the below instructions to add a new App to this repository.

**Note**, remember to replace `MC_NAME`, `WC_NAME` and `APP_*` placeholders in the instructions with the corresponding MC codename, WC name and App-related data respectively.

## Directory tree

1. Go to the `management-clusters/MC_NAME/workload-clusters/WC_NAME/apps` directory
2. Create new directory with a name corresponding to the App name
3. Go to the newly created directory and use [the kubectl-gs plugin](https://github.com/giantswarm/kubectl-gs) to generate the [App CR](https://docs.giantswarm.io/ui-api/kubectl-gs/template-app/):

```
$ kubectl gs template app \
--app-name APP_NAME \
--catalog APP_CATALOG \
--cluster WC_NAME \
--name APP_NAME \
--namespace APP_NAMESPACE \
--version APP_VERSION > appcr.yaml
```

**Note**, you can optionally configure App with the user-provided values by adding below flags to the previous command:

```
--user-configmap APP_VALUES_CM
--user-secret APP_VALUES_SECRET
```

Reference [the App Configuration](https://docs.giantswarm.io/app-platform/app-configuration/) for more details of how to properly create respective ConfigMaps or Secrets.

4. (optional) Place ConfigMap and Secrets with values as the `configmap.yaml` and `secret.enc.yaml` files respectively
5. (optional) Import the regular GPG public key of the WC and encrypt the `secret.enc.yaml` file:

```
$ gpg --import management-clusters/MC_NAME/.sops.keys/.sops.WC_NAME.asc
$ sops --encrypt --in-place management-clusters/MC_NAME/workload-clusters/WC_NAME/apps/APP_NAME/secret.enc.yaml
```

6. Go back to the `apps` directory and edit the `kustomization.yaml` there adding all the newly created files as resources:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: WC_NAME
resources:
- APP_NAME/appcr.yaml
- APP_NAME/secret.enc.yaml
- APP_NAME/configmap.yaml
```

At this point, if you have followed [the WC configuration guide](./add_wc.md), all the necessary Flux resources should already be configured.
