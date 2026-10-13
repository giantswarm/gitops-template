# Add a new Management Cluster

- [Export environment variables](#export-environment-variables)
- [Flux GPG master key pair](#flux-gpg-master-key-pair)
- [Directory tree](#directory-tree)
- [Initial cluster configuration](#initial-cluster-configuration)
- [Recommended next steps](#recommended-next-steps)

Follow the instructions below to add a new management cluster to this repository. You need to have a valid connection
(`kube.config`) to the Management Cluster. The instructions respect the [repository structure](./repo_structure.md).

In general, we have to complete 3 major steps to provide the necessary structure for a new MC:

1. [Preparing master GPG key pair](#flux-gpg-master-key-pair) to encrypt individual encryption keys of Workload Clusters
   you'll be [creating](add_wc.md) later. These keys are needed to put Secret objects in a secure manner into the GitOps
   repository itself.
1. [Preparing directory tree](#directory-tree) - which shows files, directories and their layout that are needed to complete
   our configuration.
1. [Initial configuration](#initial-cluster-configuration) that shows what objects do we have to create on the Management
   Cluster to bootstrap our GitOps management process.

*Note: As always, instructions here respect the [repository structure](./repo_structure.md).*

## Export environment variables

**Note**, the cluster codename and the GitOps repository are needed in multiple places across these instructions, the
least error prone way of providing them is by exporting them as environment variables:

```sh
export MC_NAME=YOUR_CODENAME
# name of the Flux GitRepository CR pointing at this repository, a valid Kubernetes name
export GITOPS_REPO=YOUR_GITOPS_REPO_NAME
# HTTPS URL of this repository
export GITOPS_REPO_URL=https://github.com/YOUR_ORG/YOUR_REPO
```

## Flux GPG master key pair

**Note**, `kubectl gs gitops add management-cluster --gen-master-key` can generate the master key pair together with
the directory tree, see `kubectl gs gitops add management-cluster --help`. The steps below do it by hand.

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

1. Create and apply Kubernetes `Secret` to the management cluster API using the private key:

    ```sh
    kubectl config use-context gs-$MC_NAME
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-master \
    --namespace=default \
    --from-file=${MC_NAME}.master.asc=/dev/stdin
    ```

1. Add the private key to a safe encrypted storage of your choice, for example your password manager. You will need
   it again whenever you change the encrypted keys of this management cluster, see
   [Add a new Organization](./add_org.md).

    For example, with the 1Password CLI (`op`), store it as the body of a secure note. The `jq` filter wraps the
    armored key into the item template, in the `notesPlain` field of a secure note:

    ```sh
    eval $(op signin)
    gpg --export-secret-keys --armor "${KEY_FP}" |
    jq -Rs '{"fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "label": "notesPlain", "value": .}]}' |
    op item create --vault 'Dev Common' --category securenote --title "GPG private key (${MC_NAME}, master, Flux)" --format json -
    ```

    To import the key back into your keychain later, read the note body:

    ```sh
    op item get "GPG private key (${MC_NAME}, master, Flux)" --vault 'Dev Common' --format json |
    jq -j '.fields[] | select(.id == "notesPlain") | .value' |
    gpg --import
    ```

1. Add the automatic key selection rule to the `creation_rules` list of the
   [SOPS configuration file](/.sops.yaml). `yq` creates the list if the file is new or empty:

    ```sh
    touch .sops.yaml
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/secrets/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }]' .sops.yaml
    ```

## Directory tree

1. Go to the `management-clusters` directory
1. Create new directory with a name corresponding to the MC codename:

    ```sh
    mkdir ${MC_NAME}
    ```

1. Go to the newly created directory and create 3 sub-directories there:

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

1. Save the `sops-gpg-master` `Secret` from the [previous section](#flux-gpg-master-key-pair) to the `secrets` directory:

   ```sh
   gpg --export-secret-keys --armor "${KEY_FP}" |
   kubectl create secret generic sops-gpg-master \
   --dry-run=client \
   --namespace=default \
   --from-file=${MC_NAME}.master.asc=/dev/stdin \
   -o yaml > secrets/${MC_NAME}.gpgkey.enc.yaml
   ```

1. Encrypt `sops-gpg-master` `Secret` with a GPG master public key:

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
    - ${MC_NAME}.gpgkey.enc.yaml
    EOF
    ```

1. Create the main `Kustomization` custom resource for the cluster:

    ```sh
    cat <<EOF > ${MC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-gitops
      namespace: default
    spec:
      decryption:
        provider: sops
        secretRef:
          name: sops-gpg-master
      serviceAccountName: automation
      prune: false
      interval: 1m
      path: "./management-clusters/${MC_NAME}"
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
      timeout: 2m
    EOF
    ```

1. Delete the private key from the keychain (make sure you don't leave any unencrypted or local copies of the private
   master key! This is *essential* for your GitOps deployment security!):

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

## Initial cluster configuration

Once all the above steps are completed, the management cluster's `Flux` can be initially configured to work against this
repository.

Bear in mind `Flux` needs credentials to read the repository when it is private. The steps below keep them in the
`github-https-credentials` Kubernetes `Secret` in the `default` namespace.

1. Create a GitHub token that can read the repository, for example a
   [fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
   limited to this repository with read-only `Contents` permission, and export it:

    ```sh
    export GITHUB_TOKEN=YOUR_TOKEN
    ```

1. Create the `Secret` with [flux create secret git](https://fluxcd.io/flux/cmd/flux_create_secret_git/). GitHub
   accepts the token as the password of any user name:

    ```sh
    flux create secret git github-https-credentials \
    --namespace=default \
    --url=${GITOPS_REPO_URL} \
    --username=git \
    --password="${GITHUB_TOKEN}"
    ```

    To use an SSH deploy key instead, see the SSH examples on the same page, and use the `ssh://` URL in the
    `GitRepository` below.

1. Create a GitRepository CR:

    ```sh
    cat <<EOF | kubectl apply -f -
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: GitRepository
    metadata:
      name: ${GITOPS_REPO}
      namespace: default
    spec:
      interval: 1m
      url: ${GITOPS_REPO_URL}
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

1. Apply the cluster's `Kustomization` custom resource (CR):

    ```sh
    kubectl apply -f management-clusters/${MC_NAME}/${MC_NAME}.yaml
    ```

After completing these steps, you are no longer required to interact with `Flux` directly. Further configuration,
e.g. additional sources, more Kustomize CRs, Helm-related CRs, can be entirely provided through the repository.

## Recommended next steps

- [Add a new Organization](./add_org.md)
