# Add a new Organization

- [Export environment variables](#export-environment-variables)
- [Directory tree](#directory-tree)
- [Create a regular GPG key pair for encrypting Organization' secrets (optional step)](#create-a-regular-gpg-key-pair-for-encrypting-organization-secrets-optional-step)
- [Recommended next steps](#recommended-next-steps)

Follow the below instructions to add a new Organization to this repository. Organizations are created within the
[Management Cluster's configuration](./add_mc.md) directory and in turn are meant to include
[Workload Cluster](add_wc.md) definitions (more details about the layout are available in
[repository structure](./repo_structure.md) doc).

## Export environment variables

**Note**, management cluster codename and organization name are needed in multiple places across this instruction, the
least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
```

## Directory tree

1. Go to the management cluster's `organizations` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations
    ```

1. Create a new directory with a name corresponding to the organization name:

    ```sh
    mkdir ${ORG_NAME}
    ```

1. Go to the newly created directory and create the `workload-clusters` directory there:

    ```sh
    cd ${ORG_NAME}
    mkdir workload-clusters
    ```

1. Create the mandatory `kustomization.yaml` under `workload-clusters` directory and populate it with empty resources
   for now:

    ```sh
    cat <<EOF > workload-clusters/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    ```

1. Create the Organization CR,

    directly:

    ```sh
    cat <<EOF > ${ORG_NAME}.yaml
    apiVersion: security.giantswarm.io/v1alpha1
    kind: Organization
    metadata:
      name: ${ORG_NAME}
    spec: {}
    status: {}
    EOF
    ```

    or with `kubectl gs`:

    ```sh
    kubectl gs template organization --name ${ORG_NAME} > ${ORG_NAME}.yaml
    ```

After completing all the steps, you can open a pull request with the changes. Once it is merged, `Flux` should automatically
reconcile your new organization.

## Create a regular GPG key pair for encrypting organization' secrets (optional step)

Each management cluster comes with a master GPG key-pair that is always available to encrypt your organization's
data. However, in case you wish to increase security by cryptographic splitting, and hence encrypting different data
with different keys you can follow the instructions below. It will guide you through creation and configuration of a
new GPG key-pair dedicated for an organization.

1. Generate a GPG key with no passphrase (`%no-protection`):

    ```sh
    export KEY_NAME="${ORG_NAME}"
    export KEY_COMMENT="${ORG_NAME} Flux Secrets"

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

1. Share the new GPG public key in this repository:

    ```sh
    gpg --export --armor "${KEY_FP}" \
    > management-clusters/${MC_NAME}/.sops.keys/.sops.${ORG_NAME}.asc
    ```

1. Configure automatic key selection rule in the [SOPS configuration file](/.sops.yaml):

    ```sh
    cat <<EOF >> .sops.yaml
      - path_regex: management-clusters/${MC_NAME}/organizations/${ORG_NAME}/secrets/.*\.enc\.yaml
        encrypted_regex: ^(data|stringData)$
        pgp: ${KEY_FP}
    EOF
    ```

1. Import the management cluster's master GPG private key from your safe storage into your keychain. In our example, we're
going to use 1Password (`op` CLI tool) for that:

    ```sh
    eval $(op signin)
    gpg --import \
    <(op item get --vault 'Dev Common' "GPG private key (${MC_NAME}, master, Flux)" --reveal --fields notesPlain)
    ```

1. Decrypt the `${MC_NAME}.gpgkey.enc.yaml` file with SOPS:

    ```sh
    sops --decrypt --in-place management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Update `${MC_NAME}.gpgkey.enc.yaml` file with the new organization's private key:

    ```sh
    (
    cat <<EOF
    data:
      ${MC_NAME}.${ORG_NAME}.asc: $(gpg --export-secret-keys --armor "${KEY_FP}" | base64)
    EOF
    ) | kubectl patch \
    --dry-run=client \
    -f management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml \
    --patch-file=/dev/stdin \
    -o yaml > management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml.new
    ```

1. Replace old `${MC_NAME}.gpgkey.enc.yaml` file:

    ```sh
    mv management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml.new \
    management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Re-encrypt the secret:

    ```sh
    sops --encrypt --in-place management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Push changes to the repository and wait for `Flux` to reconcile the secret. After that,
`Flux` should be ready to decrypt and reconcile the organization's secrets.

1. Go to the organization's directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}
    ```

1. Create the `secrets` directory for storing your secret data, and enter it:

    ```sh
    mkdir secrets
    cd secrets
    ```

1. Place your Kubernetes Secret into this directory and encrypt it with SOPS.
SOPS encryption rule configured earlier ensures it will get encrypted with the Organization's key:

    ```sh
    sops --encrypt --in-place management-clusters/${MC_NAME}/organizations/${ORG_NAME}/secrets/secret.enc.yaml
    ```

1. Push changes to the repository.

## Recommended next steps

- [Add a new Workload Cluster](./add_wc.md)
