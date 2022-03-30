# Update an existing App

Follow the below instructions to update an existing App.

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and App name are needed in multiple places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
```

## Update App CR

1. Go to the App directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

2. Edit the `appcr.yaml` if you want to update the App CR fields, like version, catalog, etc. For all the supported fields reference [the App CRD schema](https://docs.giantswarm.io/ui-api/management-api/crd/apps.application.giantswarm.io/)

## Update ConfigMap-based user values

1. Go to the App directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

2. Edit the `configmap.yaml` if you want to update a non-secret user configuration

## Update Secret-based user values

1. Go to the App directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

2. Import the WC' regular GPG private key into your keychain:

```sh
gpg --import \
<(lpass show --notes "Shared-Dev Common/GPG private key (${MC_NAME}, ${WC_NAME}, Flux)")
```

3. Decrypt the `secret.enc.yaml` file with SOPS:

```sh
sops --decrypt --in-place secret.enc.yaml
```

4. Grab the `.data.values` field from the Secret and base64-decode it:

```sh
yq r secret.enc.yaml data.values | base64 -d > values.tmp.yaml
```

5. Edit the `values.tmp.yaml` if you want to update a secret user configuration
6. Save the base64-encoded `values.tmp.yaml` into variable:

```sh
export NEW_USER_VALUES=$(cat values.tmp.yaml | base64)
```

7. Replace Secret's `.data.values` with new value:

```sh
yq -i eval ".data.values = \"${NEW_USER_VALUES}\"" secret.enc.yaml
```

8. Remove the `values.tmp.yaml`:

```sh
rm values.tmp.yaml
```

9. Re-encrypt the Kubernetes Secret:

```sh
sops --encrypt --in-place secret.enc.yaml
```

10. Remove the private GPG key from your keychain and submit the PR.
