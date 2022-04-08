# Add Workload Cluster instance (vintage)

This doc explains how to create an actual Cluster infrastructure instance. A pre-request for this step is to complete
[cluster structure](./add_wc_structure.md) preparation step.

## Export environment variables

**Note**, Management Cluster codename, Organization name and Workload Cluster name are needed in multiple places across
this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
```

## Pick your Cluster Template

First step needed to create a Cluster instance is to pick a cluster template it will be based on. Templates are available
as Kustomize bases in the [bases](../bases/) directory. There's also
[documentation about how to create them](./add_wc_cluster_template.md) if the base you need doesn't yet exist.

## Creating cluster based on vintage cluster template

1. Go to the Workload Cluster definition directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/cluster
    ```

1. Create the `kustomization.yaml` referencing the base template:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${CLUSTER_PATH}
    #- ${NODEPOOL_PATH}
    EOF
    ```

    **Note**, the node pool base is commented out at this point, because Giant Swarm's **admission controllers** will complain
    if we try to create both groups at the same time. We're working on a solution. Until this is solved and support for
    the `managedBy: flux` is implemented, a workaround is to create cluster CRs and node pools CRs **in two, separate PRs**.

1. (optional) create and apply additional patches if needed.

1. Leave the `cluster` directory and go to `workload-clusters`:

    ```sh
    # cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    cd ../../
    ```

1. Edit the Kustomization CR for the workload cluster and assign values to the variables from bases, see example below:

    ```yaml
    # ${WC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
    kind: Kustomization
    ...
    spec:
      ...
      postBuild:
        substitute:
          cluster_id: "demo0"
          control_plane_id: "km2k8"
          machine_deployment_id: "bg2i8"
          organization: "gitops-demo"
          release: "16.3.1"
      ...
    ```

1. Create a Pull Request with the changes you have just done. Once it is merged and Cluster' CRs are created, revisit the
`kustomization.yaml` and uncomment node pools base:

    ```sh
    # BSD sed
    sed -i "" "s/^#-/-/" kustomization.yaml
    ```

After completing this step, you can open another PR with the changes. Once it is merged, Flux should create accompanying
node pool for your cluster.

## Recommended next steps

- [add a new App CR to the Workload Cluster](./add_appcr.md)
