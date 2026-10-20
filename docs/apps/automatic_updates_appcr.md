# Enable automatic updates of an existing App

- [Enable automatic updates of an existing App](#enable-automatic-updates-of-an-existing-app)
  - [Example](#example)
  - [Export environment variables](#export-environment-variables)
  - [Version range](#version-range)
  - [Apps created from an App Template](#apps-created-from-an-app-template)
  - [Apps from an App Set](#apps-from-an-app-set)
  - [Checking the installed version](#checking-the-installed-version)
  - [Credentials for private registries (optional)](#credentials-for-private-registries-optional)

Follow the below instructions to tell Flux to automatically update an existing App. Automatic update means
that Flux will check the chart registry for you and automatically install new chart versions as they are published.

The chart version of an App is set in its `OCIRepository`. Instead of a fixed `spec.ref.tag`, you can give it a
`spec.ref.semver` range: Flux then picks the highest chart tag that satisfies the range, checks the registry again
every `spec.interval`, and the `HelmRelease` upgrades the App as soon as a newer matching tag shows up. No other Flux
objects are needed, and Flux doesn't commit anything to this repository: the repository keeps the range, the cluster
reports the version it installed.

## Example

An example of an App with automated updates is available in
[WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/apps/hello-world-automatic-updates](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/mapi/apps/hello-world-automatic-updates/ocirepository.yaml).

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and App name are needed in
multiple places across this instruction, the least error prone way of providing them is by exporting as environment
variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
```

## Version range

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Replace the fixed version of the `OCIRepository` with a version range, for example every release from `3.0.0` on,
   but below the next major version, which might bring breaking changes:

    ```sh
    yq -i '.spec.ref = {"semver": ">=3.0.0 <4.0.0"}' ocirepository.yaml
    ```

    The resulting file should look similar to this:

    ```yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}-hello-world
      namespace: org-${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        semver: '>=3.0.0 <4.0.0'
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
    ```

    **Note**, a range only matches pre-release tags, like `3.1.0-rc.1`, if it has a pre-release comparator itself:
    `>=3.0.0-0` matches every release and pre-release from `3.0.0` on. Use `spec.ref.semverFilter` to narrow the
    matching tags down with a regular expression, see
    [Add Workload Cluster environments](../add_wc_environments.md#the-development-cluster) for an example that
    follows development builds, and the [OCIRepository docs](https://fluxcd.io/flux/components/source/ocirepositories/)
    for all the options.

## Apps created from an App Template

The `OCIRepository` of an App created from an [App Template](./add_app_template.md) is part of the Template. To enable
automatic updates for a single cluster, add a patch to the App's `kustomization.yaml` instead. The `$` of the target
name is escaped, as `kustomize` reads the name as a regular expression:

```yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref
        value:
          semver: '>=3.0.0 <4.0.0'
    target:
      kind: OCIRepository
      name: \${cluster_name}-hello-world
```

## Apps from an App Set

For an App installed through an [App Set](./app_sets.md), add the same patch to the `kustomization.yaml` of the App Set
instance, in the cluster's `mapi/app_sets/YOUR_APP_SET` directory. Kustomize applies the instance's patches after the
App Set Template's, so the range replaces the version the App Set pins, for this cluster only. Bear in mind that an
App Set usually pins its versions on purpose, because its apps are known to work well together at those versions.

## Checking the installed version

The repository only holds the range. To see which version Flux picked, check the `OCIRepository` and `HelmRelease` on
the Management Cluster:

```sh
kubectl get ocirepositories,helmreleases -n org-${ORG_NAME}
```

## Credentials for private registries (optional)

Charts from the Giant Swarm catalog are public. If your chart is in a private registry, give the `OCIRepository`
credentials to read it.

1. Export path to the Docker registry config with credentials:

    ```sh
    export DOCKER_CONFIG_JSON=PATH
    ```

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Create Kubernetes Secret with Docker Registry credentials in the organization namespace, where the `OCIRepository`
   lives, and save it into a file:

    ```sh
    kubectl create secret docker-registry \
    ${WC_NAME}-${APP_NAME}-pull-secret \
    --namespace org-${ORG_NAME} \
    --from-file .dockerconfigjson=${DOCKER_CONFIG_JSON} \
    --dry-run=client \
    -o yaml > pullsecret.enc.yaml
    ```

1. Import the Workload Cluster's GPG public key and encrypt the Kubernetes Secret with it:

    ```sh
    gpg --import "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc"
    sops --encrypt --in-place pullsecret.enc.yaml
    ```

1. Reference the Secret in the `OCIRepository`:

    ```sh
    yq -i ".spec.secretRef.name = \"${WC_NAME}-${APP_NAME}-pull-secret\"" ocirepository.yaml
    ```

1. Add the Secret to the resources of the App's `kustomization.yaml`:

    ```sh
    yq -i '.resources += ["pullsecret.enc.yaml"]' kustomization.yaml
    ```
