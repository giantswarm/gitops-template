# Add a new management cluster

Follow the below instructions to add a new management cluster to this repository.

**Note**, remember to replace `MC_NAME` and `WC_NAME` in the instructions with the corresponding MC codename and WC name respectively.

## Flux GPG master key pair

**Note**, temporarily there is no automation behind creating master keys. This however may be subject to change.

A master GPG keypair is used for en- and decryption of other GPG keys kept in this repository, that are in turn used to en- and decrypt real user-related data.

1. Generate a GPG key with no passphrase (`%no-protection`):

```
$ export KEY_NAME="MC_NAME"
$ export KEY_COMMENT="MC_NAME Flux Master"

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
      XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

$ export KEY_FP=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

3. Create Kubernetes Secret with the private key:

```
$ gpg --export-secret-keys --armor "${KEY_FP}" |
kubectl create secret generic sops-gpg-master \
--namespace=flux-system \
--from-file=sops.asc=/dev/stdin
```

4. Add the private key to LastPass as a secure note:

```
$ gpg --export-secret-keys --armor "${KEY_FP}" |
lpass add --notes --non-interactive "Shared-Dev Common/GPG private key (MC_NAME, master, Flux)"
```

5. Delete the private key from the keychain:

```
$ gpg --delete-secret-keys "${KEY_FP}"
```

6. Configure automatic key selection rule in the [SOPS configuration file](../.sops.yaml):

```
creation_rules:
  - path_regex: management-clusters/MC_NAME/management-cluster/.*\.enc\.yaml
    encrypted_regex: ^(data|stringData)$
    pgp: XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

```

## Directory tree

1. Go to the `management-clusters` directory
2. Create new directory with a name corresponding to the MC codename
3. Go to the newly created directory and create 3 sub-directories there:
* `.sops.keys` - storage for all GPG public keys,
* `management-cluster` - storage for the MC configuration,
* `workload-clusters` - storage for the WCs configuration.
4. Share the master GPG public key from the [previous section](#flux-gpg-master-key-pair):

```
$ gpg --export --armor "${KEY_FP}" \
> management-clusters/MC_NAME/.sops.keys/.sops.master.asc
```

5. Go to the `management-cluster` directory and create 2 sub-directories there:
* `flux-system` - storage for the Flux configuration. Flux's resemblance of ArgoCD's App-of-Apps concept,
* `secrets` - storage for encrypted secrets, including regular GPG private keys.
6. Go to the `flux-system` directory and create 2 files there:
* `secrets.yaml` - Flux's Kustomization CR for secrets reconciliation,
* `kustomization.yaml` - Kustomize binary-related configuration file.
7. Populate the `secrets.yaml` file with the below content:

```
apiVersion: kustomize.toolkit.fluxcd.io/v1beta1
kind: Kustomization
metadata:
  name: MC_NAME-secrets
  namespace: flux-system
spec:
  serviceAccountName: kustomize-controller
  prune: false
  interval: 1m
  path: "./management-clusters/MC_NAME/management-cluster/secrets"
  sourceRef:
    kind: GitRepository
    name: workload-clusters-fleet
  timeout: 2m
  decryption:
    provider: sops
    secretRef:
      name: sops-gpg-master
```

**Note**, `prune` is set to `false` so that once the keys are delivered, they won't be deleted even if this Kustomization CR is removed from the cluster. Note also we use the previously created `sops-gpg-master` to decrypt other keys.

8. Populate the `kustomization.yaml` with the below content:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: flux-system
resources:
- secrets.yaml
```

9. Leave the `flux-system` directory and go to the `secret` directory, then create the `kustomizations.yaml` file there and fill it with the below content:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
```

## Initial cluster configuration

Once all the above steps are completed, the MC's Flux can be initially configured to work against this repository.

Bare in mind Flux needs GitHub credentials since the repository is private. This instruction assumes such credentials are available in the `github-giantswarm-https-credentials` Kubernetes Secret.

1. Create a GitRepository CR:

```
apiVersion: source.toolkit.fluxcd.io/v1beta1
kind: GitRepository
metadata:
  name: workload-clusters-fleet
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/giantswarm/workload-clusters-fleet
  secretRef:
    name: github-giantswarm-https-credentials
  ref:
    branch: main
  ignore: |
    /**
    !/management-clusters/MC_NAME/**
    /**.md
```

2. Create the _master_ Kustomization CR pointing to the `flux-system` directory:

```
apiVersion: kustomize.toolkit.fluxcd.io/v1beta1
kind: Kustomization
metadata:
  name: MC_NAME-gitops
  namespace: flux-system
spec:
  serviceAccountName: kustomize-controller
  prune: true
  interval: 1m
  path: "./management-clusters/MC_NAME/management-cluster/flux-system"
  sourceRef:
    kind: GitRepository
    name: workload-clusters-fleet
  timeout: 2m
```

After completing these steps, you are no longer required to interact with Flux directly. Further configuration, e.g. additional sources, more Kustomize CRs, Helm-related CRs, can be entirely provided through the `flux-system` directory.
