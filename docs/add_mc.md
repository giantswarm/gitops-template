# Add a new Management Cluster

- [Export Management Cluster codename](#export-management-cluster-codename)
- [Flux GPG master key pair](#flux-gpg-master-key-pair)
- [Directory tree](#directory-tree)
- [Initial cluster configuration](#initial-cluster-configuration)
- [Recommended next steps](#recommended-next-steps)

Follow the instructions below to add a new management cluster to this repository. You need to have a valid connection
(`kube.config`) to the Management Cluster. The instructions respect the [repository structure](./repo_structure.md).

In general, we have to complete 3 major steps to provide the necessary structure for a new MC:

1. [Preparing master GPG key pair](#flux-gpg-master-key-pair) to encrypt individual encryption keys of Workload Clusters
   you'll be [creating](add_wc.md) later. These keys are needed to put Secret objects in a secure manner into the gitops
   repository itself.
1. [Preparing directory tree](#directory-tree) - which shows files, directories and their layout that are needed to complete
   our configuration.
1. [Initial configuration](#initial-cluster-configuration) that shows what objects do we have to create on the Management
   Cluster to bootstrap our gitops management process.

*Note: As always, instructions here respect the [repository structure](./repo_structure.md).*

## Export Management Cluster codename

**Note**, cluster codename is needed in multiple places across these instructions, the least error prone way of providing
it is by exporting it as an environment variable:

```sh
export MC_NAME=YOUR_CODENAME
```

## Flux GPG master key pair

**Note**, temporarily there is no automation behind creating master keys. This however may be subject to change.

A master GPG keypair is used for en- and decryption of other GPG keys kept in this repository, that are in turn used to
en- and decrypt real user-related data.

1. Generate a GPG key with no passphrase (`%no-protection`):

    ```sh
    export KEY_NAME="${MC_NAME}"
    export KEY_COMMENT="${MC_NAME} Flux Master"

    gpg --batch --full-generate-key <<EOF
    %no-protection
    Key-Type: EDDSA
    Key-Curve: ed25519
    Key-Usage: sign
    Subkey-Type: ECDH
    Subkey-Curve: cv25519
    Subkey-Usage: encrypt
    Expire-Date: 0
    Name-Comment: ${KEY_COMMENT}
    Name-Real: ${KEY_NAME}
    EOF
    ```

1. Retrieve the key fingerprint and store it in an environment variable:

    ```sh
    gpg --list-secret-keys "${KEY_NAME}"
    ```

    The command above should produce the output like:

    ```text
    pub   ed25519 2021-11-25 [SC]
          XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    uid   ...
    sub   cv25519 2021-11-25 [E]
    ```

    Now, export the fingerprint:

    ```sh
    export KEY_FP=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    ```

1. Create Kubernetes Secret with the private key:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-master \
    --namespace=default \
    --from-file=${MC_NAME}.master.asc=/dev/stdin
    ```

1. Add the private to a safe encrypted storage of your choice. For example, to export the key to `LastPass`
   as a secure note, you can run:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    lpass add --notes --non-interactive "Shared-Dev Common/GPG private key (${MC_NAME}, master, Flux)"
    ```

1. Delete the private key from the keychain (make sure you don't leave any unencrypted or local copies of the private
   master key! This is *essential* for your GitOps deployment security!):

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

1. Add the automatic key selection rule to the `creation_rules` section of the [SOPS configuration file](/.sops.yaml):

    ```sh
    cat <<EOF >> .sops.yaml
    - path_regex: management-clusters/${MC_NAME}/secrets/.*\.enc\.yaml
      encrypted_regex: ^(data|stringData)$
      pgp: ${KEY_FP}
    EOF
    ```

## Directory tree

1. Go to the `management-clusters` directory
1. Create new directory with a name corresponding to the MC codename:

    ```sh
    mkdir ${MC_NAME}
    ```

1. Go to the newly created directory and create 2 sub-directories there:

    - `.sops.keys` - storage for all GPG public keys,
    - `organizations` - storage for MC organizations,
    - `secrets` - storage for encrypted secrets, including regular GPG private keys.

    ```sh
    cd ${MC_NAME}
    mkdir \
    .sops.keys \
    organizations  \
    secrets
    ```

1. Share the master GPG public key from the [previous section](#flux-gpg-master-key-pair):

    ```sh
    gpg --export --armor "${KEY_FP}" \
    > .sops.keys/.sops.master.asc
    ```

1. Save the `sops-gpg-master` Secret from the [previous section](#flux-gpg-master-key-pair) to the `secrets` directory:

   ```sh
   gpg --export-secret-keys --armor "${KEY_FP}" |
   kubectl create secret generic sops-gpg-master \
   --dry-run=client \
   --namespace=default \
   --from-file=${MC_NAME}.master.asc=/dev/stdin \
   -o yaml > secrets/${MC_NAME}.gpgkey.enc.yaml
   ```

1. Encrypt `sops-gpg-master` Secret with a GPG master public key:

    ```sh
    gpg --import .sops.keys/.sops.master.asc
    sops --encrypt --in-place secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Create the `kustomization.yaml` file under `secrets` directory and populate it with the below content:

    ```sh
    cat <<EOF > secrets/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${MC_NAME}.master.gpgkey.enc.yaml
    EOF
    ```

1. Create the main Kustomization CR for the cluster:

    ```sh
    cat <<EOF > ${MC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-gitops
      namespace: default
    spec:
      serviceAccountName: automation
      prune: false
      interval: 1m
      path: "./management-clusters/${MC_NAME}"
      sourceRef:
        kind: GitRepository
        name: YOUR_REPO
      timeout: 2m
    EOF
    ```

## Initial cluster configuration

Once all the above steps are completed, the MC's Flux can be initially configured to work against this repository.

Bear in mind Flux needs GitHub credentials since the repository is private. This instruction assumes such credentials are
available in the `github-https-credentials` Kubernetes Secret, created according to the
[FluxCD installation intranet page](https://intranet.giantswarm.io/docs/support-and-ops/installation-setup-guide/fluxcd-installation/#create-a-secret-for-private-repository-access)
in the `default` namespace.

1. Create a GitRepository CR:

    ```sh
    cat <<EOF | kubectl apply -f -
    apiVersion: source.toolkit.fluxcd.io/v1beta2
    kind: GitRepository
    metadata:
      name: GITOPS_REPO  # TODO: set as needed
      namespace: default
    spec:
      interval: 1m
      url: https://github.com/GITOPS_REPO  # TODO: set as needed
      secretRef:
        name: github-https-credentials
      ref:
        branch: main
      ignore: |
        **
        !management-clusters/${MC_NAME}/**
        !bases/**
        **.md
    EOF
    ```

1. Apply the cluster's Kustomization CR:

    ```sh
    kubectl apply -f management-clusters/${MC_NAME}/${MC_NAME}.yaml
    ```

After completing these steps, you are no longer required to interact with Flux directly. Further configuration,
e.g. additional sources, more Kustomize CRs, Helm-related CRs, can be entirely provided through the repository.

## Recommended next steps

- [Add a new Organization](./add_org.md)
