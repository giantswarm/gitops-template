# Add a new Organization

- [Export environment variables](#export-environment-variables)
- [Directory tree](#directory-tree)
- [Create a regular GPG key pair for encrypting Organization' secrets (optional step)](#create-a-regular-gpg-key-pair-for-encrypting-organization-secrets-optional-step)
- [Recommended next steps](#recommended-next-steps)

Follow the below instructions to add a new Organization to this repository. Organizations are created within the
[Management Cluster's configuration](./add_mc.md) directory and in turn are meant to include
[Workload Cluster](add_wc.md) definitions (more details about the layout are available in
[repository structure](./reference/repo-structure.md) doc).

## Export environment variables

The organisation's name is set once in the repository, as the name of its `Organization`. The organisation's
`kustomization.yaml` copies it everywhere else Flux needs it, see
[The organisation's name](./reference/repo-structure.md#the-organisations-name). The commands below still need the
management cluster codename and the organisation's name for paths and file names, so export them as environment
variables:

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

1. Create the Organization CR. Deleting it deletes the organization's namespace, with every cluster in it, so the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation keeps Flux from deleting it when its file is deleted,
   and the `giantswarm.io/prevent-deletion` label stops anyone deleting it until the label is removed, see
   [How it works](./how-it-works.md). Create it directly:

    ```sh
    cat <<EOF > ${ORG_NAME}.yaml
    apiVersion: security.giantswarm.io/v1alpha1
    kind: Organization
    metadata:
      annotations:
        kustomize.toolkit.fluxcd.io/prune: disabled
      labels:
        giantswarm.io/prevent-deletion: "true"
      name: ${ORG_NAME}
    spec: {}
    status: {}
    EOF
    ```

    or with `kubectl gs`, 6.0.0 or newer, see [kubectl-gs version](./appendices.md#kubectl-gs-version):

    ```sh
    kubectl gs template organization --name ${ORG_NAME} > ${ORG_NAME}.yaml
    ```

    `kubectl gs` doesn't write the annotation or the label yet. Add them:

    ```sh
    yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
      .metadata.labels["giantswarm.io/prevent-deletion"] = "true"' ${ORG_NAME}.yaml
    ```

1. Create the organisation's `kustomization.yaml`. It lists the `Organization` and `workload-clusters`, and copies
   the `Organization`'s name into the workload clusters' Flux `Kustomization`s: into `organization` in their
   `spec.postBuild.substitute`, which every one of them writes and which fails the build where it's missing, and
   wherever they name the organisation's namespace as `org-ORG_NAME`. The replacements win over what the files say.
   `org-ORG_NAME` is a fixed placeholder: the quoted `'EOF'` keeps it, and everything else in the file, as it is, so
   don't replace it with your organisation's name. The health check replacement applies only to a `Kustomization`
   with the label `giantswarm.io/health-check-cluster: "true"`, whose health check keeps the placeholder namespace, as
   kustomize fails on one without a health check. See
   [The organisation's name](./reference/repo-structure.md#the-organisations-name), which also says how to do without
   the replacements:

    ```sh
    cat <<'EOF' > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - ORGANIZATION_FILE
      - workload-clusters
    replacements:
      - source:
          group: security.giantswarm.io
          kind: Organization
          fieldPath: metadata.name
        targets:
          - select:
              group: kustomize.toolkit.fluxcd.io
              kind: Kustomization
            fieldPaths:
              - spec.postBuild.substitute.organization
      - source:
          group: security.giantswarm.io
          kind: Organization
          fieldPath: metadata.name
        targets:
          - select:
              group: kustomize.toolkit.fluxcd.io
              kind: Kustomization
              labelSelector: giantswarm.io/health-check-cluster=true
            fieldPaths:
              - spec.healthChecks.[kind=Cluster].namespace
            options:
              delimiter: "-"
              index: 1
      - source:
          group: security.giantswarm.io
          kind: Organization
          fieldPath: metadata.name
        targets:
          - select:
              namespace: org-ORG_NAME
            fieldPaths:
              - metadata.namespace
            options:
              delimiter: "-"
              index: 1
    EOF
    yq -i '.resources[0] = "'"${ORG_NAME}"'.yaml"' kustomization.yaml
    ```

    Flux applies the organisation's directory as this file builds it, so list here anything else you add to the
    directory, such as `secrets` below. To see what Flux applies, build the directory, not `workload-clusters` on its
    own, which leaves the placeholders:

    ```sh
    kubectl kustomize .
    ```

After completing all the steps, you can open a pull request with the changes. Once it is merged, `Flux` should automatically
reconcile your new organization.

## Create a regular GPG key pair for encrypting organization' secrets (optional step)

Each management cluster comes with a master GPG key-pair that is always available to encrypt your organization's
data. However, in case you wish to increase security by cryptographic splitting, and hence encrypting different data
with different keys you can follow the instructions below. It will guide you through creation and configuration of a
new GPG key-pair dedicated for an organization.

1. Go back to the root of the repository, as the commands below use paths relative to it:

    ```sh
    cd ../../../..
    ```

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
    touch .sops.yaml
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/'"${ORG_NAME}"'/secrets/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }]' .sops.yaml
    ```

1. Import the management cluster's master GPG private key from your safe storage into your keychain. In our example, we're
going to use 1Password (`op` CLI tool) for that:

    ```sh
    eval $(op signin)
    op item get "GPG private key (${MC_NAME}, master, Flux)" --vault 'Dev Common' --format json |
    jq -j '.fields[] | select(.id == "notesPlain") | .value' |
    gpg --import
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
      ${MC_NAME}.${ORG_NAME}.asc: $(gpg --export-secret-keys --armor "${KEY_FP}" | base64 | tr -d '\n')
    EOF
    ) | kubectl patch \
    --local \
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

1. Add the organization's private key to a safe encrypted storage of your choice, for example 1Password:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    jq -Rs '{"fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "label": "notesPlain", "value": .}]}' |
    op item create --vault 'Dev Common' --category securenote --title "GPG private key (${MC_NAME}, ${ORG_NAME}, Flux)" --format json -
    ```

1. Delete the organization's and the master private keys from the keychain:

    ```sh
    export MASTER_KEY_FP=$(gpg --show-keys --with-colons management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc |
    awk -F: '/^fpr/{print $10; exit}')
    gpg --delete-secret-keys "${KEY_FP}" "${MASTER_KEY_FP}"
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

1. List the directory in the organisation's `kustomization.yaml`, which Flux builds the organisation's directory
   from, and give it a `kustomization.yaml` of its own that lists the Secret:

    ```sh
    yq -i '.resources += ["secrets"]' ../kustomization.yaml
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - secret.enc.yaml
    EOF
    ```

1. Place your Kubernetes Secret into this directory, for example:

    ```sh
    kubectl create secret generic my-secret \
    --namespace=org-${ORG_NAME} \
    --from-literal=token=CHANGE_ME \
    --dry-run=client \
    -o yaml > secret.enc.yaml
    ```

1. Encrypt it with SOPS. The SOPS encryption rule configured earlier ensures it will get encrypted with the
Organization's key. It names the real namespace, `org-${ORG_NAME}`, not the placeholder `org-ORG_NAME`: the
replacement would change the encrypted file, which breaks its MAC, so Flux couldn't decrypt it:

    ```sh
    sops --encrypt --in-place secret.enc.yaml
    ```

1. Push changes to the repository.

## Give every workload cluster a secret store

External Secrets Operator (ESO) on the management cluster can read Secrets from a workload cluster and push Secrets to
it, through a `SecretStore` that reaches the cluster's API server. Rather than adding that store and its credentials to
Git for each new cluster, let a Kyverno `Policy`, managed with GitOps like everything else here, react to every new
cluster and generate them from the kubeconfig Secret Cluster API writes for it. The example in
[organizations/ORG_NAME/workload-cluster-secret-stores](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-cluster-secret-stores/)
has two files, both in the organisation's namespace, since customers on a Giant Swarm management cluster can't create
cluster-scoped objects:

- `policy.yaml`: the Kyverno `Policy` `generate-eso-cluster-auth-from-kubeconfig`, with two `generate` rules that chain:
    1. Every kubeconfig Secret Cluster API writes for a cluster gets an `ExternalSecret` that reads it through
       `default` and writes the client certificate and key, the cluster's CA and its API server into
       `<cluster>-eso-cluster-auth`, as `tls.crt`, `tls.key`, `ca.crt` and `server`. The rule matches the Secret by
       its type, `cluster.x-k8s.io/secret`, its `cluster.x-k8s.io/cluster-name` label and its name,
       `<cluster>-kubeconfig`, so the other Secrets Cluster API writes for the cluster, such as its CA or the
       `<cluster>-user-kubeconfig` of an EKS cluster, don't match.
    1. Every `<cluster>-eso-cluster-auth` Secret gets a `SecretStore` `<cluster>-eso-cluster-store` that reaches the
       workload cluster with them. It reads and writes Secrets in the workload cluster's `default` namespace: the
       `org-*` namespaces exist only on the management cluster. Change `remoteNamespace` to use another one that exists
       on every cluster.

    The rules name the namespace they generate in, `org-ORG_NAME`, rather than templating it: for a templated namespace
    Kyverno checks the rights of the policy's author and of its own controllers across the whole cluster, which a
    customer can't grant. `generateExisting: true` covers the clusters that exist already, and `synchronize: true`
    deletes the generated objects again when the cluster's kubeconfig Secret goes. Deleting the policy, or its file from
    Git, which Flux then prunes, deletes every store and `ExternalSecret` it generated at once, and ESO deletes each
    `<cluster>-eso-cluster-auth` Secret with the `ExternalSecret` that owns it (`creationPolicy: Owner`): the apps'
    `ExternalSecret`s and `PushSecret`s that use the stores stop syncing until the policy is back, though the Secrets
    they already wrote stay.
- `secret-store.yaml`: the `SecretStore` `default` that the generated `ExternalSecret`s read the kubeconfig Secrets
  through. It reads the organisation's namespace as the `automation` ServiceAccount Giant Swarm's rbac-operator creates
  there.

Kyverno's background controller, the ServiceAccount `kyverno-background-controller` in `kyverno`, needs rights in the
organisation's namespace to manage the `ExternalSecret`s and `SecretStore`s the policy generates and to read the
kubeconfig Secrets that trigger it. Giant Swarm's rbac-operator grants them in every organisation's namespace, with the
ClusterRole `write-kyverno-generated-externalsecrets`, so the example doesn't. Without them, Kyverno rejects the policy.

The organisation's `kustomization.yaml` lists the directory, and its replacements complete `org-ORG_NAME` in the
objects' namespace, in the namespace the policy generates in and in the one the `default` store reads, see
[The organisation's name](reference/repo-structure.md#the-organisations-name). A cluster's apps then read from or push
to the cluster with `secretStoreRef: {kind: SecretStore, name: <cluster>-eso-cluster-store}` in the organisation's
namespace. For another organisation, copy the directory into its own and list it in its `kustomization.yaml`.

### Push a Secret into a workload cluster

The `out-of-band-no-flux` cluster's apps have an example that uses its generated store:
[apps/pushed-password/pushed-password.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-password/pushed-password.yaml).
External Secrets Operator's `Password` generator makes a password, so no value is kept in Git, and a `PushSecret` in
`org-${organization}` writes it through `${cluster_name}-eso-cluster-store` into the Secret `pushed-password`, key
`password`, in the workload cluster's `default` namespace. `updatePolicy: IfNotExists` keeps the first password there,
though the generator makes a new one at every refresh. The cluster's apps Kustomization applies the example once the
cluster is ready; if Kyverno and ESO haven't made the store yet, ESO retries the `PushSecret` until they have.

To push a Secret into another cluster, copy the file into that cluster's `apps/` directory and list it in its
`apps/kustomization.yaml`: `${cluster_name}` and `${organization}` come from the cluster's apps Kustomization, so the
store name follows the cluster. To push a Secret you already have instead of a generated one, replace the
`selector.generatorRef` with `selector.secret.name`, remove the `Password`, and use `updatePolicy: Replace`, ESO's
default, so that a change to the Secret, such as a rotation, reaches the workload cluster.

## Recommended next steps

- [Add a new Workload Cluster](./add_wc.md)
