# Add Workload Cluster instance (CAPx/CAPI)

- [Example](#example)
- [Creating cluster based on existing bases](#creating-cluster-based-on-existing-bases)
- [Recommended next steps](#recommended-next-steps)

This doc explains how to create an actual Cluster infrastructure instance. A pre-request for this step is to complete
[cluster structure](./add_wc_structure.md) preparation step.

## Example

An example of a workload cluster instance created using the CAPI is available in [WC_NAME/mapi/cluster](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/mapi/cluster/).

## Creating cluster based on existing bases

1. Export environment variables

    **Note**, Management Cluster codename, Organization name and Workload Cluster name are needed in multiple places
    across this instruction, the least error prone way of providing them is by exporting as environment variables.
    `CLUSTER_PATH` is a variable pointing to a directory with a cluster base, for example the
    [template](/bases/clusters/capa/template) base or a versioned one created with
    [Add a CAPx Workload Cluster template](./guides/cluster-templates.md):

    ```sh
    export MC_NAME=CODENAME
    export ORG_NAME=ORGANIZATION
    export WC_NAME=CLUSTER_NAME
    export CLUSTER_PATH=bases/clusters/capa/template
    ```

    To create a cluster together with a set of apps from an environment template instead, see
    [Add Workload Cluster environments](./guides/environments.md).

1. Go to the Workload Cluster definition directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/cluster
    ```

1. Pick the Giant Swarm release the cluster runs. List the releases available on the Management Cluster, then read
   the version of the cluster chart that the chosen release ships, `cluster-aws` for the `aws` releases:

    ```sh
    kubectl get releases.release.giantswarm.io
    export RELEASE_VERSION=36.1.0
    export CLUSTER_APP_VERSION=$(kubectl get releases.release.giantswarm.io aws-${RELEASE_VERSION} -o yaml |
    yq '.spec.components[] | select(.name == "cluster-aws") | .version')
    ```

    The cluster needs both: the release in its values, and the matching chart version on its App CR. Without the
    release, the App fails with an error saying the release should not be empty. When upgrading the cluster later,
    change both together.

1. Prepare the cluster values. They have to set the release; everything else is optional and only overrides the
   defaults of the Management Cluster:

    ```sh
    export USERCONFIG_VALUES=/tmp/values
    cat <<EOF > ${USERCONFIG_VALUES}
    global:
      metadata:
        description: My GitOps Cluster
      nodePools:
        nodepool0:
          instanceType: m6i.xlarge
      release:
        version: ${RELEASE_VERSION}
    EOF
    ```

    The values follow the `values.yaml` schema of the cluster chart, `cluster-aws` in this example. The default apps
    of the cluster are configured in the same values, under `global.apps`.

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

1. Create patch for applying user-config values and setting the cluster chart version of the release:

    ```sh
    cat <<EOF > patch_userconfig.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: \${cluster_name}
      namespace: org-\${organization}
    spec:
      version: "${CLUSTER_APP_VERSION}"
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

1. Leave the `cluster` directory and go to `workload-clusters`:

    ```sh
    # cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    cd ../../../
    ```

1. Edit the Kustomization CR for the workload cluster and assign values to the variables from bases, see example below:

    ```yaml
    # cat ${WC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    ...
    spec:
      ...
      postBuild:
        substitute:
          cluster_description: "My GitOps Cluster"
          cluster_name: "demo0"
          organization: "gitops-demo"
      ...
    ```

1. Create a Pull Request with the changes you have just done. Once it is merged, Flux should reconcile resources
you have just created.

## Recommended next steps

- [Managing Apps installed in clusters with GitOps](./guides/README.md)
