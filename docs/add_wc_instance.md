# Add Workload Cluster instance (CAPx/CAPI)

- [Example](#example)
- [Creating cluster based on existing bases](#creating-cluster-based-on-existing-bases)
- [Recommended next steps](#recommended-next-steps)

This doc explains how to create an actual Cluster infrastructure instance. A pre-request for this step is to complete
[cluster structure](./add_wc_structure.md) preparation step.

## Example

An example of a WC cluster instance created using the CAPI is available in [WC_NAME/mapi/cluster](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/mapi/cluster/).

## Creating cluster based on existing bases

1. Export environment variables

**Note**, Management Cluster codename, Organization name and Workload Cluster name are needed in multiple places across
this instruction, the least error prone way of providing them is by exporting as environment variables. `CLUSTER_PATH`
is a variable pointing to a directory with a cluster template base.

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export CLUSTER_PATH=bases/cluster_templates/XYZ
```

1. Go to the Workload Cluster definition directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/cluster
    ```

1. If you need to customize cluster configuration, prepare the values overrides and export its path. Find example below:

    ```yaml
    # cat /tmp/values
    clusterDescription: My GitOps Cluster
    cloudConfig: my-cloud-config
    ```

    Export the path to the file:

    ```sh
    export USERCONFIG_VALUES=/tmp/values
    ```

1. Create a `ConfigMap` out of the values overrides:

    ```sh
    cat <<EOF > cluster_userconfig.yaml
    apiVersion: v1
    data:
      values: |
    $(cat ${USERCONFIG_VALUES} | sed 's/^/    /')
    kind: ConfigMap
    metadata:
      name: \${cluster_name}-userconfig
      namespace: org-\${organization}
    EOF
    ```

1. Create patch for applying user-config values:

    ```sh
    cat <<EOF > patch_userconfig.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: \${cluster_name}
      namespace: org-\${organization}
    spec:
      userConfig:
        configMap:
          name: \${cluster_name}-userconfig
          namespace: org-\${organization}
    EOF
    ```

1. Create the `kustomization.yaml` referencing base and newly created files:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    commonLabels:
      giantswarm.io/managed-by: flux
    kind: Kustomization
    patchesStrategicMerge:
      - patch_userconfig.yaml
    resources:
    - ../../../../../../../../${CLUSTER_PATH}
    - cluster_userconfig.yaml
    EOF
    ```

1. (optional) Repeat the same steps if you need to customize default apps App.

1. Leave the `cluster` directory and go to `workload-clusters`:

    ```sh
    # cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    cd ../../../
    ```

1. Edit the Kustomization CR for the workload cluster and assign values to the variables from bases, see example below:

    ```yaml
    # cat ${WC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
    kind: Kustomization
    ...
    spec:
      ...
      postBuild:
        substitute:
          cluster_name: "demo0"
          organization: "gitops-demo"
          cluster_release: "0.8.0"
          default_apps_release: "0.2.0"
      ...
    ```

1. Create a Pull Request with the changes you have just done. Once it is merged, Flux should reconcile resources
you have just created.

## Recommended next steps

- [Managing Apps installed in clusters with GitOps](./apps/README.md)
