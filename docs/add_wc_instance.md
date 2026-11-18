# Add Workload Cluster instance (CAPx/CAPI)

- [Example](#example)
- [Creating a cluster from the CAPA cluster base](#creating-a-cluster-from-the-capa-cluster-base)
- [Recommended next steps](#recommended-next-steps)

This doc explains how to create an actual Cluster infrastructure instance. A pre-request for this step is to complete
[cluster structure](./add_wc_structure.md) preparation step.

## Example

An example of a workload cluster instance created from the CAPA cluster base is in
[WC_NAME/mapi/cluster](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/mapi/cluster/).

## Creating a cluster from the CAPA cluster base

The [CAPA cluster base](/bases/clusters/capa/template) deploys the `release-aws` chart with a Flux `OCIRepository` and
`HelmRelease`. Its chart version is the Giant Swarm release, so the release lives in the Kustomization CR in git, and
you upgrade the cluster by changing it there. The chart sets the release in the values itself.

There's a `release-aws` chart for every release from v34.0.0 on. Older releases and Release CRs created by hand have
none. They need the `cluster-aws` chart as an App CR, which this repository no longer supports, see the
[App Platform deprecation](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/).

The steps below write `cluster_userconfig.yaml`, `patch_cluster_userconfig.yaml` and a `${cluster_name}-cluster-userconfig`
ConfigMap, the same names `kubectl gs gitops add workload-cluster --cluster-user-config` uses, so you can also let the
CLI create them. It needs kubectl-gs 6.0.0 or newer, see [kubectl-gs version](./appendices.md#kubectl-gs-version).

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
    export CLUSTER_PATH=bases/clusters/capa/template
    ```

    Pick the cluster's region from [bases/environments/regions](/bases/environments/regions). Every cluster needs one:
    without it, the chart takes the region of the Management Cluster's nodes, and CI fails. See
    [Regions](./guides/environments.md#regions) to add a region.

    ```sh
    export REGION=eu_central
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
    cat <<EOF > cluster_userconfig.yaml
    apiVersion: v1
    data:
      values: |
    $(cat ${USERCONFIG_VALUES} | sed 's/^/    /')
    kind: ConfigMap
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-cluster-userconfig
      namespace: org-\${organization}
    EOF
    ```

1. Create a patch that appends the `ConfigMap` to the `valuesFrom` of the base's `HelmRelease`. Values later in the
   list win, so yours override the base's:

    ```sh
    cat <<EOF > patch_cluster_userconfig.yaml
    - op: add
      path: /spec/valuesFrom/-
      value:
        kind: ConfigMap
        name: \${cluster_name}-cluster-userconfig
        valuesKey: values
    EOF
    ```

1. Create the `kustomization.yaml` referencing the base, the region and the newly created files. kustomize applies
   the region component before the patch, so the region comes before your values in `valuesFrom`, and yours win. If
   `kubectl gs gitops add workload-cluster` wrote the file, only add the `components:` list. kubectl-gs still writes
   the deprecated `commonLabels`; to match the example, move its labels under `labels:` as one `- pairs:` entry.
   `kustomize edit fix` converts it too, but also sets `includeSelectors: true`:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    components:
      - ../../../../../../../../bases/environments/regions/${REGION}
    kind: Kustomization
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
    patches:
      - path: patch_cluster_userconfig.yaml
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \\\${cluster_name}
    resources:
      - ../../../../../../../../${CLUSTER_PATH}
      - cluster_userconfig.yaml
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

1. If the cluster gets apps, make them wait for it, as the
   [WC_NAME](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml) example does. Set
   the Kustomization's `path` to `mapi/cluster`, its `timeout` to `30m`, and add a health check of the cluster:

    ```yaml
    spec:
      healthCheckExprs:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          current: status.conditions.filter(c, c.type == 'Available').all(c, c.status == 'True')
      healthChecks:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          name: demo0
          namespace: org-gitops-demo
    ```

    Then add `${WC_NAME}_APPS.yaml` for `mapi/apps`, with the same `postBuild` and the cluster's Kustomization in
    `dependsOn`, as in [WC_NAME_APPS.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_APPS.yaml),
    and list it in `kustomization.yaml`. See [Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations)
    for the order. `kubectl gs gitops add workload-cluster` still writes a single Kustomization for all of `mapi`.

1. Create a Pull Request with the changes you have just done. Once it is merged, Flux should reconcile resources
you have just created.

## Recommended next steps

- [Managing Apps installed in clusters with GitOps](./guides/README.md)
