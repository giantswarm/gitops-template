# Add a new workload cluster

Follow the below instructions to add a new workload cluster to this repository.

**Note**, remember to replace `MC_NAME` and `WC_NAME` in the instructions with the corresponding MC codename and WC name respectively.

## (optional) Flux GPG regular key pair

If you intend to keep a secret data in this repository you need to encrypt them with Mozilla SOPS. In order to do it, you need to first generate a regular GPG keypair and deliver it to the cluster. Follow the below instructions in order to do it.

1. Generate a GPG key with no passphrase (`%no-protection`):

```
$ export KEY_NAME="WC_NAME"
$ export KEY_COMMENT="WC_NAME Flux Secrets"

$ gpg --batch --full-generate-key <<EOF
%no-protection
Key-Type: 1
Key-Length: 4096
Subkey-Type: 1
Subkey-Length: 4096
Expire-Date: 0
Name-Comment: ${KEY_COMMENT}
Name-Real: ${KEY_NAME}
EOF
```

2. Retrieve the key fingerprint and store it in an environment variable:

```
$ gpg --list-secret-keys "${KEY_NAME}"

sec   rsa4096 2021-11-25 [SC]
      YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY

$ export KEY_FP=YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
```

3. Save the private key as a Kubernetes Secret into the MC configuration directory:

```
$ gpg --export-secret-keys --armor "${KEY_FP}" |
kubectl create secret generic sops-gpg-WC_NAME \
--dry-run=client \
--namespace=flux-system \
--from-file=sops.asc=/dev/stdin \
-o yaml > management-clusters/MC_NAME/management-cluster/secrets/WC_NAME/gpgkey.enc.yaml
```

4. Import the master GPG public key and encrypt the Kubernetes Secret with it:

```
$ gpg --import management-clusters/MC_NAME/.sops.keys/.sops.master.asc
$ sops --encrypt --in-place management-clusters/MC_NAME/management-cluster/secrets/WC_NAME/gpgkey.enc.yaml
```

5. Add the private key to LastPass as a secure note:

```
$ gpg --export-secret-keys --armor "${KEY_FP}" |
lpass add --notes --non-interactive "Shared-Dev Common/GPG private key (MC_NAME, WC_NAME, Flux)"
```

6. Delete the private key from the keychain:

```
$ gpg --delete-secret-keys "${KEY_FP}"
```

7. Share the regular GPG public key in this repository:

```
gpg --export --armor "YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY" \
> management-clusters/MC_NAME/.sops.keys/.sops.WC_NAME.asc
```

8. Configure automatic key selection rule in the [SOPS configuration file](../.sops.yaml):

```
creation_rules:
  - path_regex: management-clusters/MC_NAME/workload-clusters/WC_NAME/.*\.enc\.yaml
    encrypted_regex: ^(data|stringData)$
    pgp: YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
```

## Directory tree

1. Go to the `management-clusters/MC_NAME/workload-clusters` directory
2. Create a new directory with name corresponding to the WC name
3. Go to the newly created directory and create the `apps` directory there
4. Go to the `apps` directory and create 2 files there:
* `cluster_config.yaml` - common configuration for all the Apps,
* `kustomization.yaml` - Kustomize binary-related configuration file.
5. Populate the `cluster_config.yaml` file with the below content:

```
apiVersion: application.giantswarm.io/v1alpha1
kind: App
metadata:
  labels:
    giantswarm.io/managed-by: flux
  name: ignored
spec:
  config:
    configMap:
      name: WC_NAME-cluster-values
      namespace: WC_NAME
  kubeConfig:
    inCluster: false
    secret:
      name: WC_NAME-kubeconfig
      namespace: WC_NAME
    context:
      name: WC_NAME
```

**Note**, the `giantswarm.io/managed-by: flux` label is very important here, it tells app-admission-controller to ignore missing ConfigMaps and Secrets set in `spec.userConfig` of the App CRs.

6. Populate the `kustomization.yaml` file with the below content:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: WC_NAME
patches:
- path: cluster_config.yaml
  target:
    kind: App
```

## MC configuration

1. Go to the `management-clusters/MC_NAME/management-cluster/flux-system` directory
2. Create the `WC_NAME` directory and the `appcr.yaml` file inside, and then populate it with the below content:

```
apiVersion: kustomize.toolkit.fluxcd.io/v1beta1
kind: Kustomization
metadata:
  name: MC_NAME-WC_NAME-apps
  namespace: flux-system
spec:
  serviceAccountName: kustomize-controller
  prune: false
  interval: 1m
  path: "./management-clusters/MC_NAME/workload-clusters/WC_NAME/apps"
  sourceRef:
    kind: GitRepository
    name: workload-clusters-fleet
  dependsOn:
  - name: MC_NAME-secrets
  decryption:
    provider: sops
    secretRef:
      name: sops-gpg-WC_NAME
  timeout: 1m
```

3. Edit the `kustomization.yaml` in the `flux-system` directory adding the newly created file as a resource:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: flux-system
resources:
- secrets.yaml
- WC_NAME/appcr.yaml

```

After completing all the steps, you can open a PR with the changes. Once it is merged, Flux should automatically configure itself to reconcile apps in your WC.
