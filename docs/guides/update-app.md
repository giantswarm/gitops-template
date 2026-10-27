# Update an existing App

- [Update an existing App](#update-an-existing-app)
  - [Export environment variables](#export-environment-variables)
  - [Updating App](#updating-app)
    - [Updating the chart version](#updating-the-chart-version)
    - [Updating the HelmRelease](#updating-the-helmrelease)
    - [Updating ConfigMap-based user values](#updating-configmap-based-user-values)
    - [Updating Secret-based user values](#updating-secret-based-user-values)
  - [Apps from an App Set](#apps-from-an-app-set)

Follow the below instructions to update an existing App.

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and App name are needed in multiple
places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
```

## Updating App

  App update and reconfiguration must be done in a correct resource:

- the chart version lives in the `OCIRepository`, in the `ocirepository.yaml` file,
- how the chart is installed, for example the target namespace, timeouts or retries, lives in the `HelmRelease`, in
  the `helmrelease.yaml` file,
- plain text configuration lives in the `-user-values` ConfigMap, generated from the `override_config.yaml` file,
- encrypted configuration lives in the `-user-secrets` Secret, in the `secret.enc.yaml` file.

  For an App created from an [App Template](./app-templates.md), the `ocirepository.yaml` and `helmrelease.yaml`
  files are part of the Template. Changing them there changes the App in every cluster that uses the Template. To change
  them for a single cluster, add a patch to the App's `kustomization.yaml`, see
  [Adding App using App Template](./add-app.md#adding-app-using-app-template).

  For an App installed through an App Set, see [Apps from an App Set](#apps-from-an-app-set).

### Updating the chart version

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Set the new chart version in the `OCIRepository`:

    ```sh
    yq -i '.spec.ref.tag = "NEW_VERSION"' ocirepository.yaml
    ```

    To have Flux pick up new versions by itself, use a version range instead, see
    [Enable automatic updates of an existing App](./automatic-updates.md).

### Updating the HelmRelease

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Edit the `helmrelease.yaml`. For all the supported fields reference
   [the HelmRelease documentation](https://fluxcd.io/flux/components/helm/helmreleases/).

### Updating ConfigMap-based user values

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Edit the `override_config.yaml` if you want to update a non-secret user configuration

### Updating Secret-based user values

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/apps/${APP_NAME}
    ```

1. Import the WC's regular GPG private key from your safe storage into your keychain. In our example, we're gonna
   use 1Password's CLI `op` for that:

    ```sh
    eval $(op signin)
    op item get "GPG private key (${MC_NAME}, ${WC_NAME}, Flux)" --vault 'Dev Common' --format json |
    jq -j '.fields[] | select(.id == "notesPlain") | .value' |
    gpg --import
    ```

1. Decrypt the `secret.enc.yaml` file with SOPS:

    ```sh
    sops --decrypt --in-place secret.enc.yaml
    ```

1. Edit the values under `.stringData.values` if you want to update a secret user configuration.

    If the Secret holds them base64-encoded under `.data.values` instead, as Secrets created with
    `kubectl create secret` do, decode them into a temporary file, edit it, and encode them back:

    ```sh
    yq eval .data.values secret.enc.yaml | base64 -d > values.tmp.yaml
    # edit values.tmp.yaml
    export NEW_USER_VALUES=$(base64 < values.tmp.yaml | tr -d '\n')
    yq -i eval ".data.values = \"${NEW_USER_VALUES}\"" secret.enc.yaml
    rm values.tmp.yaml
    ```

1. Re-encrypt the Kubernetes Secret:

    ```sh
    sops --encrypt --in-place secret.enc.yaml
    ```

1. Remove the private GPG key from your keychain and submit the PR.

    ```sh
    export KEY_FP=$(gpg --show-keys --with-colons \
    "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc" |
    awk -F: '/^fpr/{print $10; exit}')
    gpg --delete-secret-keys "${KEY_FP}"
    ```

## Apps from an App Set

An App installed through an [App Set](./app-sets.md) has no `mapi/apps/${APP_NAME}` directory. Its files are in the
directory of the App Set instance, `mapi/app_sets/YOUR_APP_SET`, next to the instance's `kustomization.yaml`:

- plain text configuration is in the `override_config_<app>.yaml` file, for example `override_config_hello_world.yaml`,
  which the instance's `configMapGenerator` turns into the `${cluster_name}-${APP_NAME}-user-values` ConfigMap,
- encrypted configuration is in the `${cluster_name}-${APP_NAME}-user-secrets` Secret, an encrypted file in the same
  directory that is listed under `resources:` in its `kustomization.yaml`. Edit it with the steps of
  [Updating Secret-based user values](#updating-secret-based-user-values), run in that directory and with that file
  in place of `secret.enc.yaml`,
- the `OCIRepository` and the `HelmRelease` come from the App Set Template, which usually pins the chart version of
  every app in the set. Changing them there changes the App in every cluster that uses the set.

To change the chart version for a single cluster, add a patch on the `OCIRepository` to the instance's
`kustomization.yaml`. Kustomize applies it after the App Set Template's own version patch, so it replaces the pinned
version for this cluster only. The `$` of the target name is escaped, as `kustomize` reads the name as a regular
expression:

```yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        value: "NEW_VERSION"
    target:
      kind: OCIRepository
      name: \${cluster_name}-hello-world
```

To follow a version range instead, see
[Enable automatic updates of an existing App](./automatic-updates.md#apps-from-an-app-set).
