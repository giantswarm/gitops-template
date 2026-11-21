# Cluster bases

The cluster from the [basic tutorial](../basic/getting-started.md) is built from a cluster base,
[bases/clusters/capa](/bases/clusters/capa), with nothing of its own but a name, a release and a region. A base holds
what many clusters share, so each cluster only adds what's different. It deploys the cluster's `release-<provider>`
chart with a Flux `OCIRepository` and `HelmRelease`, and the chart version is the Giant Swarm release, from the
`${release}` variable.

Sooner or later your clusters share more than the chart's defaults: the same node pools, say, on every cluster of a
team. Writing those into each cluster works, until someone changes three of the five. This tutorial puts them into a
base of your own instead, next to the CAPA one, and creates a second cluster from it.

- [Choose a base](#choose-a-base)
- [Create a base with your own defaults](#create-a-base-with-your-own-defaults)
- [Create a cluster from it](#create-a-cluster-from-it)
- [Next steps](#next-steps)

A cluster's values come in layers, in the order of its `HelmRelease`'s `valuesFrom`, and later layers win: the
management cluster's values, the base's, the region's, and the cluster's own last.
[Cluster values](../../reference/values.md#cluster-values) has the list.

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## Choose a base

The bases live in [bases/clusters](/bases/clusters), one directory per provider. The fork ships one, `capa`, for AWS.
It installs the `release-aws` chart, which exists for every Giant Swarm release from v34.0.0 on. Its
[readme](/bases/clusters/capa/readme.md) lists the variables it expects and how it differs from what
`kubectl gs gitops add base` writes.

For another provider, write its base first, see [Create a cluster base for another provider](../../how-to/cluster-base-provider.md).

Export the base you build on:

```sh
export PROVIDER_BASE=capa
```

## Create a base with your own defaults

Your base is an overlay of the provider's: it lists the provider's base and replaces its `${cluster_name}-config`
ConfigMap with values of its own. It goes next to the provider's base in `bases/clusters`, as a directory of its own,
never inside the provider's directory, which holds that one base and nothing else.

1. Export the name of the new base:

    ```sh
    export BASE_NAME=my-defaults
    ```

1. Create its directory:

    ```sh
    mkdir -p bases/clusters/${BASE_NAME}
    ```

1. Copy the provider's `cluster_config.yaml`. Your file replaces the provider's values as a whole, so start from a copy
   and change only what you need. A value you leave out is lost, such as `global.metadata.preventDeletion`, which puts
   the `giantswarm.io/prevent-deletion` label on the cluster's `Cluster`:

    ```sh
    cp bases/clusters/${PROVIDER_BASE}/cluster_config.yaml bases/clusters/${BASE_NAME}/cluster_config.yaml
    ```

1. Add your defaults to the copy. They follow the `values.yaml` schema of the cluster chart. For example, a node pool:

    ```sh
    yq -i '.global.nodePools.nodepool0 = {"instanceType": "m6i.xlarge", "maxSize": 10, "minSize": 3}' \
      bases/clusters/${BASE_NAME}/cluster_config.yaml
    ```

    To find more values to set, let kubectl-gs print a cluster's values, and copy the ones you need from the ConfigMap
    it prints. It reads the release from the management cluster your context points at:

    ```sh
    kubectl gs template cluster --provider capa --name example --organization ${ORG_NAME} \
      --release ${RELEASE_VERSION}
    ```

    Copy values, not the whole ConfigMap: it also has the cluster's name, its organisation and
    `global.metadata.preventDeletion: false`, which the base already sets the right way.

1. Create the `kustomization.yaml`. It lists the provider's base and replaces its ConfigMap with one generated from
   your `cluster_config.yaml`. The quoted `'EOF'` keeps the variables in the file, and `sed` fills in the provider:

    ```sh
    cat <<'EOF' | sed "s|PROVIDER_BASE|${PROVIDER_BASE}|" > bases/clusters/${BASE_NAME}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    configMapGenerator:
      - behavior: replace
        files:
          - values=cluster_config.yaml
        name: ${cluster_name}-config
        namespace: org-${organization}
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    resources:
      - ../PROVIDER_BASE
    EOF
    ```

1. Copy the provider's `readme.md`, which lists the variables the base expects, and add a line on what yours changes:

    ```sh
    cp bases/clusters/${PROVIDER_BASE}/readme.md bases/clusters/${BASE_NAME}/readme.md
    ```

1. Check that the base builds. The variables stay as they are until Flux fills them in:

    ```sh
    kubectl kustomize bases/clusters/${BASE_NAME}
    ```

The cluster `HelmRelease` and `OCIRepository` come from the provider's base untouched, with the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the `giantswarm.io/prevent-deletion` label that keep
Flux, or anyone else, from deleting the cluster by accident. If you write a base from scratch instead of an overlay,
give its `HelmRelease` and `OCIRepository` both, see [Deletion protection](../../explanation/deletion-protection.md).

## Create a cluster from it

A cluster from your base is built like the one in the basic tutorial, with your base where the CAPA one was. This one
gets no apps, so it needs only the cluster's `Kustomization`.

1. Export the new cluster's name, at most 20 characters, and its directory:

    ```sh
    export WC2_NAME=CLUSTER_NAME
    export WC2_DIR=${ORG_DIR}/workload-clusters/${WC2_NAME}
    ```

1. Create the cluster's `kustomization.yaml`. It lists your base and, as every cluster must, a region:

    ```sh
    mkdir -p ${WC2_DIR}/cluster
    cat <<EOF > ${WC2_DIR}/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    components:
      - ../../../../../../../bases/environments/regions/${REGION}
    resources:
      - ../../../../../../../bases/clusters/${BASE_NAME}
    EOF
    ```

1. Create the cluster's `Kustomization`, next to its directory in `workload-clusters`. The organisation's namespace
   `Kustomization` applies it into `org-${ORG_NAME}` and fills in `${organization}`, which the `\$` keeps in the file:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${WC2_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${WC2_NAME}
    spec:
      dependsOn:
        - name: ${MC_NAME}-organization-${ORG_NAME}
          namespace: default
      healthCheckExprs:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          current: status.conditions.exists(c, c.type == 'Available' && c.status == 'True')
      healthChecks:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          name: ${WC2_NAME}
          namespace: org-\${organization}
      interval: 10m
      path: ./${WC2_DIR}/cluster
      postBuild:
        substitute:
          cluster_description: "${WC2_NAME} from ${BASE_NAME}"
          cluster_name: "${WC2_NAME}"
          organization: "\${organization}"
          release: "${RELEASE_VERSION}"
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
        namespace: default
      timeout: 30m
    EOF
    ```

1. List it in the organisation's clusters, then commit and push the base and the cluster together:

    ```sh
    yq -i '.resources += ["'"${WC2_NAME}"'.yaml"]' ${ORG_DIR}/workload-clusters/kustomization.yaml
    git add bases/clusters/${BASE_NAME} ${ORG_DIR}/workload-clusters
    git commit -m "Add cluster base ${BASE_NAME} and cluster ${WC2_NAME}" && git push
    ```

**Check:** the new cluster comes up in 15 to 20 minutes, with your node pool:

```sh
kubectl gs get clusters -n org-${ORG_NAME}
kubectl get configmap ${WC2_NAME}-config -n org-${ORG_NAME} -o jsonpath='{.data.values}'
```

You can move your first cluster onto the base too: change `bases/clusters/capa` to `bases/clusters/${BASE_NAME}` in
`${WC_DIR}/cluster/kustomization.yaml`. Its node pools then change to the base's at the next reconciliation, and
its nodes are replaced, so pick your moment.

To give one cluster values of its own on top of the base, see
[Give a cluster its own values](../../how-to/cluster-values.md#give-a-cluster-its-own-values). To give it apps, add an
`apps` directory and an apps `Kustomization`, as in the basic tutorial's
[step 3](../basic/getting-started.md#3-create-a-workload-cluster).

## Next steps

- [Stages and regions](./stages-and-regions.md): dev, staging and prod clusters in two regions, from one base.
- [Create a cluster base for another provider](../../how-to/cluster-base-provider.md).
- [Scheduled upgrades](../advanced/scheduled-upgrades.md): move a cluster's release only inside an upgrade window.
