# Give one cluster its own values

A cluster made from a cluster base runs with the base's defaults and its region. When one cluster needs something
different, such as bigger nodes or a description, give it a values ConfigMap of its own. It's the last layer of the
cluster's values, so it wins over the base, the region and the management cluster's values, see
[Cluster values](../reference/values.md#cluster-values). When many clusters share the same change, put it in a base of
its own instead, see [Share cluster defaults](../tutorials/intermediate/cluster-bases.md).

The [WC_NAME/cluster](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/cluster/) example
has its own values.

## Write the cluster's values ConfigMap

The files have the names `kubectl gs gitops add workload-cluster --cluster-user-config` writes, so you can let it
write them, see [Workload cluster](./kubectl-gs.md#workload-cluster), and fix what it leaves out.

1. Export the names the commands use, and go to the cluster's `cluster` directory:

    ```sh
    export MC_NAME=CODENAME
    export ORG_NAME=ORGANIZATION
    export WC_NAME=CLUSTER_NAME
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/cluster
    ```

1. Write the values. Everything in them is optional and only overrides the defaults. They follow the `values.yaml`
   schema of the cluster chart, `cluster-aws` for `release-aws`. Don't set `global.release.version`, because the chart
   sets it from the release:

    ```sh
    cat <<'EOF' > /tmp/values.yaml
    global:
      metadata:
        description: My GitOps cluster
      nodePools:
        nodepool0:
          instanceType: m6i.xlarge
    EOF
    ```

1. Turn them into a ConfigMap. The `reconcile.fluxcd.io/watch` label makes Flux apply a change at once, and CI fails
   without it. `${cluster_name}` and `${organization}` stay as they are: Flux fills them in.

    ```sh
    cat <<EOF > cluster_userconfig.yaml
    apiVersion: v1
    data:
      values: |
    $(sed 's/^/    /' /tmp/values.yaml)
    kind: ConfigMap
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-cluster-userconfig
      namespace: org-\${organization}
    EOF
    ```

1. Create a patch that appends the ConfigMap to the `valuesFrom` of the base's `HelmRelease`. It appends with `/-`,
   so yours comes after the base's entries and wins:

    ```sh
    cat <<'EOF' > patch_cluster_userconfig.yaml
    - op: add
      path: /spec/valuesFrom/-
      value:
        kind: ConfigMap
        name: ${cluster_name}-cluster-userconfig
        valuesKey: values
    EOF
    ```

1. List both in the cluster's `kustomization.yaml`. kustomize applies the `components`, such as the region, before
   the patch, so the region comes before your values in `valuesFrom`, and yours win:

    ```sh
    yq -i '.resources += ["cluster_userconfig.yaml"] |
      .patches += [{"path": "patch_cluster_userconfig.yaml",
        "target": {"group": "helm.toolkit.fluxcd.io", "kind": "HelmRelease", "name": "\\${cluster_name}"}}]' \
      kustomization.yaml
    ```

    The `$` of the target name is escaped, as kustomize reads the name as a regular expression. The result looks like
    this:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    components:
      - ../../../../../../../bases/environments/regions/eu_central
    patches:
      - path: patch_cluster_userconfig.yaml
        target:
          group: helm.toolkit.fluxcd.io
          kind: HelmRelease
          name: \${cluster_name}
    resources:
      - ../../../../../../../bases/clusters/capa
      - cluster_userconfig.yaml
    ```

1. Commit and push. Flux upgrades the cluster's release with the new values.

To check the merged values before you push, see
[Render what Flux applies](./check-changes.md#render-what-flux-applies).

Maps merge with the earlier layers and lists replace them, see [Values](../reference/values.md). A node pool you add
comes on top of the region's, and a list you set, such as a node pool's `availabilityZones`, replaces the region's.

## Configure the default apps

The default apps of a cluster are part of its cluster chart, not apps in `apps`. Configure them in the same values,
under `global.apps`, the same way as the rest of the cluster configuration. The chart's `values.yaml` schema lists the
apps and what each one takes. To add an app the chart doesn't install, add
it to the cluster's `cluster/apps` or `apps` instead, see [Add an app to a cluster](./add-app.md).
