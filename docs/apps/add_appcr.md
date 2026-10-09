# Add a new App to a Workload Cluster

- [Examples](#examples)
- [Common steps](#common-steps)
  - [Export environment variables](#export-environment-variables)
  - [Setting up directory tree structure for managing apps](#setting-up-directory-tree-structure-for-managing-apps)
- [Adding App directly](#adding-app-directly)
- [Adding App using App Template](#adding-app-using-app-template)
- [Providing encrypted values](#providing-encrypted-values)
- [Listing the App in the cluster](#listing-the-app-in-the-cluster)
- [Recommended next steps](#recommended-next-steps)

Follow the instructions below to add a new App to a cluster managed in this repository.
You can add an App directly (without any intermediate step) or use an [App Template](add_app_template.md).
The documentation below shows common steps as well as what is different in both cases.

An app is a Flux `HelmRelease` that installs a Helm chart into the workload cluster, and an `OCIRepository` that
points at the chart. Its values come in layers, listed in the `HelmRelease`'s `spec.valuesFrom`: the cluster values,
the App Template defaults (only for apps created from a template), and two optional per-cluster overrides, the
`-user-values` ConfigMap and the `-user-secrets` Secret.

## Examples

Examples of creating apps are available in following locations:

- An example of a directly configured App (the simplest use case - no configuration): an [app without configuration](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/apps/hello-world/)
- An example of an app created from an App Template, with plain and SOPS-encrypted (`secret.enc.yaml`) overrides, is
  available in [WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/apps/envoy-gateway-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/apps/envoy-gateway-from-template/).

## Common steps

Please follow these steps when installing an App directly as well as using App Template.

### Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and the App name are needed
in multiple places across this instruction, the least error prone way of providing them is by exporting as environment
variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
```

`APP_NAME` is used in the names of the app's resources, which all get the `${cluster_name}-` prefix, so the same app
can be deployed to several clusters of an organization. When using an App Template, it has to be the app name the
template uses, for example `hello-world` for [bases/apps/hello-world](/bases/apps/hello-world/).

### Setting up directory tree structure for managing apps

1. Go to the `apps` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps
    ```

1. Create new directory with a name corresponding to the App name, and enter it:

    ```sh
    mkdir ${APP_NAME}
    cd ${APP_NAME}
    ```

## Adding App directly

1. Set remaining env variables:

    ```sh
    export APP_CHART=APP_CHART          # name of the chart in the registry, for example `hello-world`
    export APP_VERSION=APP_VERSION      # chart version (OCI tag), for example `3.2.2`
    export APP_NAMESPACE=APP_NAMESPACE  # namespace in the workload cluster the app is installed into
    ```

1. Create the `OCIRepository` that points at the chart. The example uses the Giant Swarm catalog, change the `url` to
   use a chart from another registry:

    ```sh
    cat <<EOF > ocirepository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        tag: ${APP_VERSION}
      url: oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART}
    EOF
    ```

1. Create the `HelmRelease` that installs the chart into the workload cluster:

    ```sh
    cat <<EOF > helmrelease.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: \${cluster_name}-${APP_NAME}
        namespace: org-\${organization}
      install:
        createNamespace: true
        remediation:
          remediateLastFailure: false
          retries: 10
      interval: 5m
      kubeConfig:
        secretRef:
          name: \${cluster_name}-kubeconfig
      releaseName: ${APP_NAME}
      storageNamespace: ${APP_NAMESPACE}
      targetNamespace: ${APP_NAMESPACE}
      timeout: 10m
      upgrade:
        remediation:
          remediateLastFailure: true
          retries: 10
          strategy: rollback
      valuesFrom:
        - kind: ConfigMap
          name: \${cluster_name}-cluster-values
          valuesKey: values
        - kind: ConfigMap
          name: \${cluster_name}-${APP_NAME}-user-values
          optional: true
          valuesKey: values
        - kind: Secret
          name: \${cluster_name}-${APP_NAME}-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

1. (optional - if adding configuration) Put plain Helm values into the `override_config.yaml` file:

    ```sh
    cat <<EOF > override_config.yaml
    # values of the ${APP_CHART} chart for this cluster
    EOF
    ```

1. Create the `kustomization.yaml` of the app. The `configMapGenerator` turns `override_config.yaml` into the
   `-user-values` ConfigMap, leave it out if you didn't create the file, and list `secret.enc.yaml` only if you
   [provide encrypted values](#providing-encrypted-values):

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: \${cluster_name}-${APP_NAME}-user-values
    generatorOptions:
      disableNameSuffixHash: true
    kind: Kustomization
    namespace: org-\${organization}
    resources:
      - helmrelease.yaml
      - ocirepository.yaml
      - secret.enc.yaml # only if providing encrypted values
    EOF
    ```

1. Continue with [Listing the App in the cluster](#listing-the-app-in-the-cluster).

## Adding App using App Template

1. First, you need to pick a directory with an App Template from the [`bases/apps`](/bases/apps/) dir. Export the
path to the directory in an env variable:

    ```sh
    export APP_TEMPLATE_DIR=bases/apps/APP_TEMPLATE
    ```

    Make sure your `APP_NAME` variable is set to the exact same name as used for the app in the App Template you're
    pointing to.

1. (optional - if overriding the default config of the Template) Put the plain Helm values to change into the
   `override_config.yaml` file. Only the keys you set are changed, the rest still comes from the Template:

    ```sh
    cat <<EOF > override_config.yaml
    # values to change for this cluster
    EOF
    ```

1. In the current directory
    (`management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}`)
    create a new `kustomization.yaml` with the following content:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    ## CONFIGURATION OVERRIDE BLOCK START - include only if overriding default config from the Template
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: \${cluster_name}-${APP_NAME}-user-values
    generatorOptions:
      disableNameSuffixHash: true
    ## CONFIGURATION OVERRIDE BLOCK END
    kind: Kustomization
    namespace: org-\${organization}
    resources:
      - ../../../../../../../../../${APP_TEMPLATE_DIR}
      - secret.enc.yaml ## ONLY IF INCLUDING SECRET
    EOF
    ```

    Please note, that the block marked "configuration override block" is needed only if you override the default
    config from the Template, and the `- secret.enc.yaml` line only if you
    [provide encrypted values](#providing-encrypted-values). No patch is needed: the Template's `HelmRelease` already
    lists the `-user-values` ConfigMap and the `-user-secrets` Secret as optional layers in `spec.valuesFrom`, so
    creating them is enough.

1. Additional notes

    If you want to, you can use the same idea of App Templates to override any property of the base App Template by
    using [kustomize patches](https://kubectl.docs.kubernetes.io/references/kustomize/kustomization/patches/). For
    example, to install another chart version, patch the `OCIRepository`. The `$` of the target name is escaped, as
    `kustomize` reads the name as a regular expression:

    ```yaml
    patches:
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            value: "3.2.2"
        target:
          kind: OCIRepository
          name: \${cluster_name}-hello-world
    ```

1. Continue with [Listing the App in the cluster](#listing-the-app-in-the-cluster).

## Providing encrypted values

Values you'd rather not keep in plain text go into the `-user-secrets` Secret, encrypted with SOPS. This requires the
Workload Cluster's GPG key, see
[the WC structure guide](../add_wc_structure.md#create-flux-gpg-regular-key-pair-optional-step).

1. In the App directory, put the Helm values into the `values` key of the Secret:

    ```sh
    cat <<EOF > secret.enc.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: \${cluster_name}-${APP_NAME}-user-secrets
      namespace: org-\${organization}
    stringData:
      values: |
        # secret values of the app for this cluster
    EOF
    ```

1. Import the regular GPG public key of the Workload Cluster and encrypt the `secret.enc.yaml` file. The SOPS rule
   for the cluster picks the key:

    ```sh
    gpg --import "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc"
    sops --encrypt --in-place secret.enc.yaml
    ```

## Listing the App in the cluster

1. Go back to the `apps` directory:

    ```sh
    cd ..
    ```

1. Add the App directory to the resources of the `kustomization.yaml` there:

    ```sh
    yq -i eval ".resources += \"${APP_NAME}\" | .resources style=\"\"" kustomization.yaml
    ```

At this point, if you have followed [the WC configuration guide](../add_wc.md), all the necessary Flux resources should
already be configured. Commit the changes to the branch your Flux is using.

## Recommended next steps

- [Enable automatic updates of an existing App](./automatic_updates_appcr.md)
- [Update an existing App](./update_appcr.md)
