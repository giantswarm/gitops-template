# Add a vintage Workload Cluster template (Legacy CRs)

Follow the below instructions to store vintage cluster CRs in the repository. These CRs provide a
[Cluster Template](./add_wc_template.md) that is later used to create Cluster Definitions.

The instructions below take into account that CAPI like objects are frequently versioned (so you have `v1beta1`, `v1beta2`),
but often the changes between the versions are rather small and in practice sometimes don't even affect you.

Since CAPI objects are big in general, in this repo we have extracted a common base for some of them. This base is to
share what is common in CAPI objects across many versions. To make such bases useful, we're introducing another base on
top of them to set specific CAPI versions and version specific properties on top of the shared base.

*Note: As always, instructions here respect the [repository structure](./repo_structure.md).*

## Export environment variables

**Note**, Management Cluster codename, Organization name and Workload Cluster name are needed in multiple places across
this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
```

## Choose bases

In order to avoid code duplication, it is advised to utilize the
[bases and overlays concept](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/#bases-and-overlays)
of Kustomize in order to configure clusters and node pools.

This repository comes with some built in bases you can choose from, go to the [bases](../bases) directory and search for
some that meet your needs, then export their paths with:

```sh
export CLUSTER_PATH=CLUSTER_BASE_PATH
export NODEPOOL_PATH=NODEPOOL_BASE_PATH
```

If desired base is not there, you can add it. Reference the next section to get a general idea of how to do it.

## Create shared template base (optional)

**IMPORTANT:** template base cannot serve as a standalone base for cluster creation, it is there to abstract
configuration common across the API versions, and is then used as a base to other bases, which provide an overlay with a
specific configuration. This is to avoid code duplication across bases. If a template base for your provider is already
here, you may skip this part.

**Bear in mind**, this is not a complete guide of how to create a perfect base, but rather a mere summary of basic steps
needed to move forward. Hence, instructions here will not always be precise in telling you what to change, as this can
strongly depend on resources involved, how much out of them you would like to include into a base, etc.

1. Export provider' name and API version of cluster and node pools resources you are about to create, for example `aws`
and `v1alpha3`. Template base is not tied to any specific version, though we need to specify it for the `kubectl gs`:

    ```sh
    export PROVIDER=aws
    export API_VERSION=v1alpha3
    ```

1. Create a directory structure:

    ```sh
    mkdir -p bases/clusters/${PROVIDER}/template
    mkdir -p bases/nodepools/${PROVIDER}/template
    ```

1. Use the [kubectl gs template cluster](https://docs.giantswarm.io/ui-api/kubectl-gs/template-cluster/) to template
cluster resources, see example for the `aws` provider below. Use arbitrary values for the mandatory fields:

    ```sh
    kubectl gs template cluster --provider ${PROVIDER} \
    --name mywcl \
    --organization myorg \
    --release 17.0.3 \
    --output bases/clusters/${PROVIDER}/${API_VERSION}/cluster.yaml
    ```

1. Replace values provided in the previous step by a shell-like variables:

    ```sh
    # BSD sed
    sed -i "" 's/myorg/${organization}/g' bases/clusters/${PROVIDER}/template/cluster.yaml
    sed -i "" 's/mywcl/${cluster_id}/g' bases/clusters/${PROVIDER}/template/cluster.yaml
    sed -i "" 's/17.0.3/${release}/g' bases/clusters/${PROVIDER}/template/cluster.yaml
    ```

1. Replace API versions with a `replaceme` token:

    ```sh
    sed -i "" 's/\/v[0-9][a-z]*[0-9]$/\/replaceme/g' bases/clusters/${PROVIDER}/template/cluster.yaml
    ```

1. Open the `cluster.yaml` file in your favourite editor and take two action:

    - replace often repeating values with variables in the same manner as above. Fields to replace could be virtually anything,
    see example below, also please check the [repository structure](./repo_structure.md#flux-kustomization-crs-involved)
    and other [bases](../bases) for more,
    - remove version-specific fields, making sure template carries only a common code.

    ```yaml
    apiVersion: infrastructure.giantswarm.io/replaceme
    kind: AWSControlPlane
    metadata:
      labels:
        giantswarm.io/control-plane: ${control_plane_id}
      name: ${control_plane_id}
    spec:
      instanceType: ${cp_instance_type}
    ```

    The rule of thumb is, don't be afraid of trying different configurations. Parameterizing too much or too little can be
    resolved over time, and finding the right balance is a process.

1. Split up the `cluster.yaml` into multiple files:

    ```sh
    COUNT=$(grep -e '---' bases/clusters/${PROVIDER}/template/cluster.yaml | wc -l | tr -d ' ')
    csplit bases/clusters/${PROVIDER}/template/cluster.yaml /---/ "{$((COUNT-1))}"
    rm bases/clusters/${PROVIDER}/template/cluster.yaml
    ```

1. Rename newly created files and move them to the base:

    ```sh
    for f in $(ls xx*)
    do
        new_name=$(yq eval '.kind' $f | tr '[:upper:]' '[:lower:]')
        mv $f bases/clusters/${PROVIDER}/template/$new_name.yaml
    done
    ```

1. Create the `kustomization.yaml` under base directory, with split files as resources:

    ```sh
    cat <<EOF > bases/clusters/${PROVIDER}/template/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    $(for f in $(ls bases/clusters/${PROVIDER}/template/); do echo "- $f"; done)
    EOF
    ```

1. Create the `readme.md` with supported variables and expected values.

1. Repeat the same steps for node pools.

## Create versioned base (optional)

**IMPORTANT**, versioned bases use a shared template base and overlay it with a specific CAPI API version, and
if needed, a configuration. They provide a ready definition of a CAPI cluster that can be later used to create cluster
instances.

1. Export provider' name and API version of cluster and node pools resources you are about to create, for example `aws`
and `v1alpha3`:

    ```sh
    export PROVIDER=aws
    export API_VERSION=v1alpha3
    ```

1. Create a directory structure:

    ```sh
    mkdir -p bases/clusters/${PROVIDER}/${API_VERSION}
    mkdir -p bases/nodepools/${PROVIDER}/${API_VERSION}
    ```

1. Create the `kustostomization.yaml` under base directory, referencing template and replacing `replaceme` tokens with
specific API versions,  see example for the `aws` provider below:

    ```sh
    cat <<EOF > bases/clusters/${PROVIDER}/${API_VERSION}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    patches:
    - patch: |-
        - op: replace
          path: "/apiVersion"
          value: cluster.x-k8s.io/v1beta1
        - op: replace
          path: "/spec/infrastructureRef/apiVersion"
          value: infrastructure.giantswarm.io/${API_VERSION}
      target:
        group: cluster.x-k8s.io
        kind: Cluster
        version: replaceme
    - patch: |-
        - op: replace
          path: "/apiVersion"
          value: infrastructure.giantswarm.io/${API_VERSION}
      target:
        group: infrastructure.giantswarm.io
        kind: 'AWSCluster|AWSControlPlane'
        version: replaceme
    - patch: |-
        - op: replace
          path: "/apiVersion"
          value: infrastructure.giantswarm.io/${API_VERSION}
        - op: replace
          path: "/spec/infrastructureRef/apiVersion"
          value: infrastructure.giantswarm.io/${API_VERSION}
      target:
        group: infrastructure.giantswarm.io
        kind: G8sControlPlane
        version: replaceme
    resources:
    - ../template
    EOF
    ```

1. Copy `readme.md` from the template base:

    ```sh
    cp bases/clusters/${PROVIDER}/template/readme.md bases/clusters/${PROVIDER}/${API_VERSION}/readme.md
    ```

1. Export bases paths:

    ```sh
    export CLUSTER_PATH=CLUSTER_BASE_PATH
    export NODEPOOL_PATH=NODEPOOL_BASE_PATH
    ```

## Recommended next steps

- [adding a WC structure](./add_wc_structure.md)
- [adding a WC definition](./add_cluster_crs.md)
- [adding a new App CR to a Workload Cluster](./add_appcr.md)
