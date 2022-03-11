# Update an existing App

Follow the below instructions to update an existing App.

**Note**, remember to replace `MC_NAME`, `WC_NAME` and `APP_*` placeholders in the instructions with the corresponding MC codename, WC name and App-related data respectively.

## Update App CR

1. Go to the `management-clusters/MC_NAME/workload-clusters/WC_NAME/apps/APP_NAME` directory
2. Edit the `appcr.yaml` if you want to update the App CR fields, like version, catalog, etc. For all the supported fields reference [the App CRD schema](https://docs.giantswarm.io/ui-api/management-api/crd/apps.application.giantswarm.io/)

## Update ConfigMap-based user values

1. Go to the `management-clusters/MC_NAME/workload-clusters/WC_NAME/apps/APP_NAME` directory
2. Edit the `configmap.yaml` if you want to update a non-secret user configuration

## Update Secret-based user values

1. Go to the `management-clusters/MC_NAME/workload-clusters/WC_NAME/apps/APP_NAME` directory
2. Import the WC's regular GPG private key into your keychain:

```
$ gpg --import \
<(lpass show --notes "Shared-Dev Common/GPG private key (MC_NAME, WC_NAME, Flux)")
```

3. Decrypt the `secret.enc.yaml` file with SOPS:

```
$ sops --decrypt --in-place secret.enc.yaml
```

4. Grab the `.data.values` field from the Secret and base64-decode it:

```
$ yq r secret.enc.yaml data.values | base64 -d > values.tmp.yaml
```

5. Edit the `values.tmp.yaml` if you want to update a secret user configuration
6. Base64-encode the `values.tmp.yaml`:

```
$ cat values.tmp.yaml | base64
```

7. Replace Secret's `.data.values` with the output from the previous command
8. Remove the `values.tmp.yaml`
9. Re-encrypt the Kubernetes Secret:

```
$ sops --encrypt --in-place secret.enc.yaml
```

10. Remove the private GPG key from your keychain
