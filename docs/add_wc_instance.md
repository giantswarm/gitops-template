# Add Workload Cluster instance (CAPx/CAPI)

- [Example](#example)
- [Creating a cluster from the release base](#creating-a-cluster-from-the-release-base)
- [Recommended next steps](#recommended-next-steps)

This doc explains how to create an actual Cluster infrastructure instance. A pre-request for this step is to complete
[cluster structure](./add_wc_structure.md) preparation step.

## Example

An example of a workload cluster instance created from the release base is in
[WC_NAME_RELEASE/mapi/cluster](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_RELEASE/mapi/cluster/).

## Creating a cluster from the release base

The [release](/bases/clusters/capa/release) base deploys the `release-aws` chart with a Flux `OCIRepository` and
`HelmRelease`. Its chart version is the Giant Swarm release, so the release lives in the Kustomization CR in git, and
you upgrade the cluster by changing it there. The chart sets the release in the values itself.

There's a `release-aws` chart for every release from v34.0.0 on. Older releases and Release CRs created by hand have
none. They need the `cluster-aws` chart as an App CR, which this repository no longer supports, see the
[App Platform deprecation](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/).

1. Export environment variables:

    ```sh
    export MC_NAME=CODENAME
    ```

    ```sh
    export ORG_NAME=ORGANIZATION
    ```

    ```sh
    export WC_NAME=CLUSTER_NAME
    ```

    ```sh
    export CLUSTER_PATH=bases/clusters/capa/release
    ```

    To create a cluster together with a set of apps from an environment template instead, see
    [Add Workload Cluster environments](./guides/environments.md).

1. Go to the Workload Cluster definition directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/cluster
    ```

1. Pick the Giant Swarm release the cluster runs. First, list the releases available on the Management Cluster:

    ```sh
    kubectl get releases.release.giantswarm.io
    ```

    Then export the one you picked, without the `aws-` prefix:

    ```sh
    export RELEASE_VERSION=36.2.0
    ```

1. Prepare the cluster values. Everything in them is optional and only overrides the defaults of the Management
   Cluster. Don't set `global.release.version`, because the chart sets it:

    ```sh
    export USERCONFIG_VALUES=/tmp/values
    ```

    ```sh
    cat <<EOF > ${USERCONFIG_VALUES}
    global:
      metadata:
        description: My GitOps Cluster
      nodePools:
        nodepool0:
          instanceType: m6i.xlarge
    EOF
    ```

    The values follow the `values.yaml` schema of the `cluster-aws` chart. The default apps of the cluster are
    configured in the same values, under `global.apps`.

1. Create a `ConfigMap` out of the values overrides:

    ```sh
    cat <<EOF > cluster_user_config.yaml
    apiVersion: v1
    data:
      values: |
    $(cat ${USERCONFIG_VALUES} | sed 's/^/    /')
    kind: ConfigMap
    metadata:
      name: \${cluster_name}-user-config
      namespace: org-\${organization}
    EOF
    ```

1. Create a patch that appends the `ConfigMap` to the `valuesFrom` of the base's `HelmRelease`. Values later in the
   list win, so yours override the base's:

    ```sh
    cat <<EOF > patch_user_config.yaml
    - op: add
      path: /spec/valuesFrom/-
      value:
        kind: ConfigMap
        name: \${cluster_name}-user-config
        valuesKey: values
    EOF
    ```

1. Create the `kustomization.yaml` referencing the base and the newly created files:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    commonLabels:
      giantswarm.io/managed-by: flux
    kind: Kustomization
    patches:
      - path: patch_user_config.yaml
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \\\${cluster_name}
    resources:
      - ../../../../../../../../${CLUSTER_PATH}
      - cluster_user_config.yaml
    EOF
    ```

1. Leave the `cluster` directory and go to `workload-clusters`:

    ```sh
    cd ../../../
    ```

1. Edit the Kustomization CR for the workload cluster and set the variables of the base, `release` included:

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
          release: "36.2.0"
      ...
    ```

    Note that without `release`, the `OCIRepository` has no chart version to pull and the cluster doesn't install. To
    upgrade the cluster later, change `release` to a newer release.

1. Create a Pull Request with the changes you have just done. Once it is merged, Flux should reconcile resources
you have just created.

## Recommended next steps

- [Managing Apps installed in clusters with GitOps](./guides/README.md)
