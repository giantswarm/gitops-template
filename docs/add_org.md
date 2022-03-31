# Add a new organization

Follow the below instructions to add a new organization to this repository.

## Export environment variables

**Note**, MC codename and organization name are needed in multiple places across this instruction, the least error prone
way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
```

## Directory tree

1. Go to the MC's `organizations` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations
    ```

1. Create a new directory with a name corresponding to the organization name:

    ```sh
    mkdir ${ORG_NAME}
    ```

1. Go to the newly created directory and create the `workload-clusters` directory there:

    ```sh
    cd ${ORG_NAME}
    mkdir workload-clusters
    ```

1. Create the mandatory `kustomization.yaml` under `workload-clusters` directory and populate it with empty resources
   for now:

    ```sh
    cat <<EOF > workload-clusters/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    ```

1. Create the Organization CR,

    directly:

    ```sh
    cat <<EOF > ${ORG_NAME}.yaml
    apiVersion: security.giantswarm.io/v1alpha1
    kind: Organization
    metadata:
      name: ${ORG_NAME}
    spec: {}
    status: {}
    EOF
    ```

    or with `kubectl gs`:

    ```sh
    kubectl gs template organization --name ${ORG_NAME} > ${ORG_NAME}.yaml
    ```

After completing all the steps, you can open a PR with the changes. Once it is merged, Flux should automatically
reconcile your new organization.

## Recommended next steps

- [add a new Workload Cluster](./add_wc.md)
