# Add a CAPx (CAPI) Workload Cluster base

- [Example](#example)
- [Choose a base](#choose-a-base)
- [Create a base for another provider (optional)](#create-a-base-for-another-provider-optional)
- [Create a base with your own defaults (optional)](#create-a-base-with-your-own-defaults-optional)
- [Recommended next steps](#recommended-next-steps)

A cluster base holds what many workload clusters share, so each cluster only adds what's different. A base deploys
the cluster's `release-<provider>` chart with a Flux `OCIRepository` and `HelmRelease`. The chart version is the Giant
Swarm release, set by the `${release}` variable.

The values come in layers. Flux merges the entries of the `HelmRelease`'s `valuesFrom` in order, and later entries win:

- the base's `${cluster_name}-config` ConfigMap holds the defaults of every cluster made from the base
- a cluster appends its own ConfigMap with a patch, see
  [Creating a cluster from the release base](../add_wc_instance.md#creating-a-cluster-from-the-release-base)

The instructions respect the [repository structure](../reference/repo-structure.md).

## Example

[bases/clusters/capa/release](/bases/clusters/capa/release) is the base for CAPA clusters.

## Choose a base

Go to the [bases](/bases/clusters) directory and pick a base, then export its path:

```sh
export CLUSTER_PATH=bases/clusters/capa/release
```

The `release-aws` chart exists for every release from v34.0.0 on. Older releases and Release CRs created by hand have
no `release-<provider>` chart. They need the `cluster-<provider>` chart as an App CR, which this repository no longer
supports, see the [App Platform deprecation](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/).

## Create a base for another provider (optional)

[`kubectl gs gitops add base`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-base/) creates a base for
a provider. For example, for CAPZ:

```sh
kubectl gs gitops add base --provider capz
```

It writes `bases/clusters/capz/template` with three files:

- `cluster.yaml` with the `OCIRepository` of the `release-azure` chart and the `HelmRelease`
- `cluster_config.yaml` with the default values
- `kustomization.yaml`, which turns `cluster_config.yaml` into the `${cluster_name}-config` ConfigMap

Note that it needs kubectl-gs 6.0.0 or newer. Older versions generate an App CR.

## Create a base with your own defaults (optional)

If many clusters share settings, such as their node pools, put them in a base of their own. It's an overlay of a base
that replaces the `${cluster_name}-config` ConfigMap.

1. Export the name of the new base:

    ```sh
    export BASE_NAME=my-defaults
    ```

1. Create its directory:

    ```sh
    mkdir -p bases/clusters/capa/${BASE_NAME}
    ```

1. Write the defaults into `cluster_config.yaml`. They follow the `values.yaml` schema of the cluster chart. Keep the
   `metadata` block, because it replaces the one of the base below:

    ```sh
    cat <<'EOF' > bases/clusters/capa/${BASE_NAME}/cluster_config.yaml
    global:
      metadata:
        description: ${cluster_description}
        name: ${cluster_name}
        organization: ${organization}
      nodePools:
        nodepool0:
          instanceType: m6i.xlarge
          maxSize: 10
          minSize: 3
    EOF
    ```

    To start from complete values instead, run
    [`kubectl gs template cluster`](https://docs.giantswarm.io/reference/kubectl-gs/template-cluster/) with
    `--provider capa` and a release, and keep the values of the ConfigMap it prints.

1. Create the `kustomization.yaml`. It replaces the base's ConfigMap with one generated from `cluster_config.yaml`:

    ```sh
    cat <<'EOF' > bases/clusters/capa/${BASE_NAME}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    configMapGenerator:
      - behavior: replace
        files:
          - values=cluster_config.yaml
        name: ${cluster_name}-config
        namespace: org-${organization}
    generatorOptions:
      disableNameSuffixHash: true
    kind: Kustomization
    resources:
      - ../release
    EOF
    ```

1. Copy the `readme.md` of the base below, which lists the variables the base expects:

    ```sh
    cp bases/clusters/capa/release/readme.md bases/clusters/capa/${BASE_NAME}/readme.md
    ```

1. Export the path of the new base:

    ```sh
    export CLUSTER_PATH=bases/clusters/capa/${BASE_NAME}
    ```

## Recommended next steps

- [Prepare multiple environments](./environments.md)
- [Add a new Workload Cluster repository structure](../add_wc_structure.md)
