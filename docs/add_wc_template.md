# Add a CAPx (CAPI) Workload Cluster template (cluster App based)

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Choose bases](#choose-bases)
- [Create shared cluster template base (optional)](#create-shared-cluster-template-base-optional)
- [Create versioned base (optional)](#create-versioned-base-optional)
- [Recommended next steps](#recommended-next-steps)

Our CAPx (CAPI provider-specific clusters) are delivered by Giant Swarm as an application. It
is an `App` containing the cluster instance definition.

You can follow the instructions below to store CAPx cluster templates in the repository. The instructions respect the
[repository structure](./repo_structure.md).

Adding definitions can be done on two levels: shared cluster template and version specific template, see
[create shared template base](#create-shared-template-base-optional)
and [create versioned base](#create-versioned-base-optional).

If all you want is to create a new CAPx cluster using an existing definition,
go to the [creating cluster instance with CAPx](./add_wc_instance.md).

**IMPORTANT**, CAPx configuration utilizes the
[app platform configuration levels](https://docs.giantswarm.io/tutorials/app-platform/app-configuration/#levels),
in the following manner:

- cluster templates provide default configuration via `App'` `config` field,
- cluster instances provide custom configuration via `App'` `userConfig` field, that is overlaid on top of `config`.

See more about this approach [here](https://github.com/giantswarm/rfc/tree/main/merging-configmaps-gitops).

## Example

An example of a workload cluster template created using the CAPx/CAPI is available in [bases/clusters/capa](/bases/clusters/capa/).

## Export environment variables

**Note**, management cluster codename, organization name and workload cluster name are needed in multiple places
across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
```

## Choose bases

In order to avoid code duplication, it is advised to utilize the
[bases and overlays](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/#bases-and-overlays)
of Kustomize in order to configure the cluster.

This repository comes with some built in bases you can choose from, go to the [bases](/bases/clusters)
directory and search for some that meet your needs, then export their paths with:

```sh
export CLUSTER_PATH=CLUSTER_BASE_PATH
```

If the desired base is not there, you can add it. Reference the next sections to get a general idea of how to do it.

## Create shared cluster template base (optional)

*Note: if a template base for your provider is already here, you most probably want to skip this part.*

**IMPORTANT:** shared cluster template base cannot serve as a standalone base for cluster creation, it is there only to abstract
App CRs that are common to all clusters versions.
It is then used as a base to other bases, which provide an overlay with a specific configuration. This is to avoid
code duplication across bases.

**Bear in mind**, this is not a complete guide of how to create a perfect base, but rather a mere summary of basic
steps needed to move forward. Hence, instructions here will not always be precise in telling you what to change,
as this can strongly depend on resources involved, how much of them you would like to include into a base, etc.

1. Export provider's and CAPx names you are about to create, for example `capa` and `aws`:

    ```sh
    export CAPX=capa
    export PROVIDER=aws
    ```

1. Create a directory structure:

    ```sh
    mkdir -p bases/clusters/${CAPX}/template
    ```

1. Create cluster App CR template:

    ```sh
    cat <<EOF > bases/clusters/${CAPX}/template/cluster.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: \${cluster_name}
      namespace: org-\${organization}
    spec:
      catalog: giantswarm
      kubeConfig:
        inCluster: true
      name: cluster-${PROVIDER}
      namespace: org-\${organization}
      version: \${cluster_release}
    EOF
    ```

1. Create the template's `kustomization.yaml`, note usage of
[`ConfigMap` generator](https://github.com/kubernetes-sigs/kustomize/blob/master/examples/configGeneration.md)
for turning config from the previous step into a `ConfigMap` and placing it under the
[values](https://docs.giantswarm.io/app-platform/app-configuration/#values-format) key:

    ```sh
    cat <<EOF > bases/clusters/${CAPX}/template/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - cluster.yaml
    EOF
    ```

1. Create the `readme.md` listing variables supported and expected values:

    ```sh
    cat <<EOF > readme.md
    # Input Variables

    Expected variables are in the table below.

    | Variable | Expected Value |
    | :--: | :--: |
    | \`cluster_name\` | Unique name of the Workload Cluster, MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
    | \`organization\` | Organization name, the \`org-\` prefix MUST not be part of it and MUST comply with the [Kubernetes Names](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#names) |
    | \`cluster_release\` | Cluster app version, reference the [Cluster AWS](https://github.com/giantswarm/cluster-aws/releases) for more insight on releases |
    ```

## Create versioned base (optional)

**IMPORTANT**, versioned cluster template bases use a shared cluster template base and overlay it with a preferably
generic configuration for a given cluster version. Versioning comes from the fact that `values.yaml` schema may change
over multiple releases,
and although minor differences can be handled on the `userConfig` level, it is advised for the bases to follow major
`values.yaml` schema versions to avoid confusion.

There is an example for CAPA [2.2.0](/bases/clusters/capa/template) as major changes were introduced
to the `values.yaml` in the [cluster-aws 2.2.0 release](https://github.com/giantswarm/cluster-aws/releases/tag/2.2.0).

**IMPORTANT**, despite the below instructions referencing `kubectl-gs` for templating configuration, `kubectl-gs`
generates configuration for the most recent schema only. If you configure a base for older versions of cluster app,
it is advised to check what is generated against the version-specific `values.yaml`.

1. Export CAPx name, provider name and cluster App version you are about to create, for example `capa`, `aws` and `2.2.0`:

    ```sh
    export CAPX=capa
    export PROVIDER=AWS
    export CLUSTER_VERSION="2.2.0"
    ```

1. Create a directory structure:

    ```sh
    mkdir -p bases/clusters/${CAPX}/${VERSION}
    mkdir -p bases/nodepools/${CAPX}/${VERSION}
    ```

1. Use the [kubectl gs template cluster](https://docs.giantswarm.io/ui-api/kubectl-gs/template-cluster/) to template
cluster resources, see example for the `aws` provider below. Use arbitrary values for the mandatory fields, we
will configure them later in our process:

    ```sh
    kubectl gs template cluster \
    --release 30.0.0 \
    --name mywcl \
    --organization myorg \
    --provider capa \
    ```

1. Split up the `cluster.yaml` into multiple files:

    ```sh
    COUNT=$(grep -e '---' bases/clusters/${CAPX}/${VERSION}/cluster.tmp.yaml | wc -l | tr -d ' ')
    csplit bases/clusters/${CAPX}/${VERSION}/cluster.tmp.yaml /---/ "{$((COUNT-2))}"
    rm bases/clusters/${CAPX}/${VERSION}/cluster.tmp.yaml
    ```

1. Discard everything except `mywcl-cluster-userconfig` and move it to the base:

    ```sh
    for f in $(ls xx*)
    do
        name=$(yq eval '.metadata.name' $f | tr '[:upper:]' '[:lower:]')
        if [[ "$name" == "mywcl-cluster-userconfig" ]]
        then
            yq eval '.data.values' $f > bases/clusters/${CAPX}/${VERSION}/cluster_config.yaml
        else
            rm $f
        fi
    done
    ```

1. Replace `mywcl`, `myorg` values from the previous step with variables:

    ```sh
    sed -i "s/myorg/${organization}/g" bases/clusters/${CAPX}/${VERSION}/cluster_config.yaml
    sed -i "s/mywcl/${cluster_name}/g" bases/clusters/${CAPX}/${VERSION}/cluster_config.yaml
    ```

1. Compare `cluster_config.yaml` against the version-specific `values.yaml`, and tweak it if necessary to match the
expected schema. At this point you may also provide extra configuration, like additional availability zones, node
pools, etc.:

    ```sh
    wget https://github.com/giantswarm/cluster-aws/archive/refs/tags/${CLUSTER_VERSION}.tar.gz
    tar -xvf ${CLUSTER_VERSION}.tar.gz cluster-${PROVIDER}-${CLUSTER_VERSION:1}/helm/cluster-${PROVIDER}/values.yaml
    vim cluster-aws-${CLUSTER_VERSION:1}/helm/cluster-${PROVIDER}/values.yaml
    ```

1. Create a patch for the cluster App CR to provide the newly created configuration:

    ```sh
    cat <<EOF > bases/clusters/${CAPX}/${VERSION}/patch_config.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: \${cluster_name}
      namespace: org-\${organization}
    spec:
      extraConfigs:
        - kind: configMap
          name: \${cluster_name}-config
          namespace: org-\${organization}
          priority: 1
    EOF
    ```

1. Create the `kustomization.yaml`, referencing the template, and generating the ConfigMap out of `cluster_config.yaml`:

    ```sh
    cat <<EOF > bases/clusters/${CAPX}/${VERSION}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    configMapGenerator:
      - files:
        - values=cluster_config.yaml
        name: \${cluster_name}-config
        namespace: org-\${organization}
    generatorOptions:
      disableNameSuffixHash: true
    kind: Kustomization
    patchesStrategicMerge:
      - patch_config.yaml
    resources:
      - ../template
    EOF
    ```

1. Copy `readme.md` from the template base:

    ```sh
    cp bases/clusters/${CAPX}/template/readme.md bases/clusters/${CAPX}/${VERSION}/readme.md
    ```

1. Export bases paths:

    ```sh
    export CLUSTER_PATH=bases/clusters/${CAPX}/${VERSION}
    ```

## Recommended next steps

- [Managing Apps installed in clusters with GitOps](./apps/README.md)
