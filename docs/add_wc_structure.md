# Add a new Workload Cluster repository structure

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Create Flux GPG regular key pair (optional step)](#create-flux-gpg-regular-key-pair-optional-step)
- [Create an age key pair (optional step)](#create-an-age-key-pair-optional-step)
- [Directory tree](#directory-tree)
- [MC configuration](#mc-configuration)
- [Recommended next steps](#recommended-next-steps)

Adding a new Workload Cluster requires a few major steps in the configuration process. One of them
is to prepare the necessary structure and configuration for the GitOps repository itself.

This includes:

1. [Preparing a new, cluster-specific, Secrets encryption GPG key](#create-flux-gpg-regular-key-pair-optional-step).
1. [Preparing directory tree](#directory-tree) - which shows files, directories and their layout that are needed to complete
   our configuration.
1. [Adding our new Workload Cluster to an existing Management Cluster definition](#mc-configuration).

*Note: As always, instructions here respect the [repository structure](./reference/repo-structure.md).*

## Example

An example of a workload cluster directory structure is available in [WC_NAME/](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/).

## Export environment variables

**Note** In order to ensure consistency in the execution of this instruction, consider exporting the following
environment variables for easy reference. These represent common names used throughout these commands such as
Management Cluster codename, Organization name and Workload cluster name.

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export GIT_REPOSITORY_NAME=REPOSITORY_NAME
```

## Create Flux GPG regular key pair (optional step)

If you intend to keep a secret data for your new cluster in this repository you need to encrypt them with Mozilla SOPS.
In order to do so, you need to first generate a regular (dedicated for this single cluster) GPG keypair and deliver it
to the cluster. Follow the below instructions in order to do it.

**Important**, the instructions here will tell you how to create a single GPG key-pair for the entire WC-related
structure. If you need more granular encryption you can repeat most of the steps to produce multiple key-pair and
encryption rules for them, remember though of saving all of them under a single `${WC_NAME}.gpgkey.enc.yaml`
Kubernetes Secret, you MUST not create multiple Secrets.

1. Generate a GPG key with no passphrase (`%no-protection`):

    ```sh
    export KEY_NAME="${WC_NAME}"
    export KEY_COMMENT="${WC_NAME} Flux Secrets"

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

1. The private key goes into a Kubernetes Secret in the organisation's `namespace/secrets` directory, so it is in
   the organisation's namespace, with the cluster's `Kustomization`s that decrypt with it. If the organisation has
   no `namespace/secrets` yet, create it as [Add an organization](./add_org.md) does: its `kustomization.yaml` keeps
   Flux from deleting the keys, and `namespace/kustomization.yaml` lists it:

    ```sh
    export ORG_SECRETS=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/secrets
    if [ ! -f ${ORG_SECRETS}/kustomization.yaml ]; then
      mkdir -p ${ORG_SECRETS}
      yq -i '.resources += ["secrets"]' ${ORG_SECRETS}/../kustomization.yaml
      cat <<EOF > ${ORG_SECRETS}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    # Flux decrypts with the SOPS keys here: deleting one stops GitOps for what uses it
    commonAnnotations:
      kustomize.toolkit.fluxcd.io/prune: disabled
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
          # nobody can delete them, Flux included, until this label is removed
          giantswarm.io/prevent-deletion: "true"
    resources: []
    EOF
    fi
    ```

1. Save the private key as a Kubernetes Secret into that directory, in the organisation's namespace:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-${WC_NAME} \
    --dry-run=client \
    --namespace=org-${ORG_NAME} \
    --from-file=${WC_NAME}.main.asc=/dev/stdin \
    -o yaml > ${ORG_SECRETS}/${WC_NAME}.gpgkey.enc.yaml
    ```

1. Add the newly created secret to the resources of `${ORG_SECRETS}/kustomization.yaml`:

    ```sh
    yq -i eval ".resources += \"${WC_NAME}.gpgkey.enc.yaml\" | .resources style=\"\"" \
    ${ORG_SECRETS}/kustomization.yaml
    ```

1. Import the master GPG public key and encrypt the Kubernetes Secret with it. The management cluster's rule for the
   workload clusters' keys in `namespace/secrets`, from [Add a new Management Cluster](./add_mc.md), picks the master
   key. If your `.sops.yaml` doesn't have it, add it ahead of any rule of an organisation's own key for
   `namespace/secrets`, see [SOPS keys](./reference/sops-keys.md#encryption-rules):

    ```sh
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
    sops --encrypt --in-place ${ORG_SECRETS}/${WC_NAME}.gpgkey.enc.yaml
    ```

1. As a backup, save the private key to an external encrypted storage. As an example, you can add the private key
   to 1Password (`op` CLI tool) as a secure note:

    ```sh
    eval $(op signin)
    gpg --export-secret-keys --armor "${KEY_FP}" |
    jq -Rs '{"fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "label": "notesPlain", "value": .}]}' |
    op item create --vault 'Dev Common' --category securenote --title "GPG private key (${MC_NAME}, ${WC_NAME}, Flux)" --format json -
    ```

1. Delete the private key from the keychain:

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

1. Share the new GPG public key in this repository:

    ```sh
    gpg --export --armor "${KEY_FP}" \
    > management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc
    ```

1. Configure automatic key selection rule in the [SOPS configuration file](/.sops.yaml):

    ```sh
    touch .sops.yaml
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/'"${ORG_NAME}"'/workload-clusters/'"${WC_NAME}"'/(cluster|apps)/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }]' .sops.yaml
    ```

1. Commit the encrypted `${WC_NAME}.gpgkey.enc.yaml` in the same commit as the `secrets/kustomization.yaml` that
   lists it, together with the public key and `.sops.yaml`. If the list reaches the repository without the file,
   the organisation's namespace Kustomization fails to build and stops reconciling:

    ```sh
    git add ${ORG_SECRETS} management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/kustomization.yaml \
    management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc \
    .sops.yaml
    git status --short management-clusters/${MC_NAME}  # nothing should be left untracked (??)
    ```

## Create an age key pair (optional step)

Instead of a GPG key, the cluster can have an [age](https://github.com/FiloSottile/age) key, which is simpler to
create and handle. You need `age-keygen`. The master key stays a GPG key: it encrypts the age key like it encrypts
the GPG keys of other clusters. The example `WC_NAME` cluster uses one; see [SOPS keys](./reference/sops-keys.md).

1. Generate the key. The file holds the private key, so keep it out of the repository:

    ```sh
    age-keygen -o ${WC_NAME}.agekey
    export AGE_PUBLIC_KEY=$(age-keygen -y ${WC_NAME}.agekey)
    ```

1. Save the private key as a Kubernetes Secret into the organisation's `namespace/secrets` directory, in the
   organisation's namespace. Create the directory first if the organisation doesn't have it, as for the GPG key above.
   kustomize-controller reads age keys from Secret keys that end in `.agekey`:

    ```sh
    export ORG_SECRETS=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/secrets
    kubectl create secret generic sops-age-${WC_NAME} \
    --dry-run=client \
    --namespace=org-${ORG_NAME} \
    --from-file=${WC_NAME}.agekey=${WC_NAME}.agekey \
    -o yaml > ${ORG_SECRETS}/${WC_NAME}.agekey.enc.yaml
    ```

1. Add it to the resources of `${ORG_SECRETS}/kustomization.yaml`, and encrypt it with the master key, which the
   management cluster's rule for the workload clusters' keys picks, as for the GPG key above:

    ```sh
    yq -i eval ".resources += \"${WC_NAME}.agekey.enc.yaml\" | .resources style=\"\"" \
    ${ORG_SECRETS}/kustomization.yaml
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
    sops --encrypt --in-place ${ORG_SECRETS}/${WC_NAME}.agekey.enc.yaml
    ```

1. Save `${WC_NAME}.agekey` to an external encrypted storage, as for the GPG key above, then delete the file:

    ```sh
    rm ${WC_NAME}.agekey
    ```

1. Share the public key in this repository and add its rule to the [SOPS configuration file](/.sops.yaml):

    ```sh
    echo "${AGE_PUBLIC_KEY}" > management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.agekey.pub
    touch .sops.yaml
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/'"${ORG_NAME}"'/workload-clusters/'"${WC_NAME}"'/(cluster|apps)/.*\\.enc\\.yaml",
      "age": "'"${AGE_PUBLIC_KEY}"'"
    }]' .sops.yaml
    ```

1. Commit the encrypted Secret, `secrets/kustomization.yaml`, the public key and `.sops.yaml` together:

    ```sh
    git add ${ORG_SECRETS} management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/kustomization.yaml \
    management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.agekey.pub \
    .sops.yaml
    git status --short management-clusters/${MC_NAME}  # nothing should be left untracked (??)
    ```

The cluster's `Kustomization`, below, names `sops-age-${WC_NAME}` in `decryption.secretRef`. A `Kustomization` reads
one Secret: to use a GPG and an age key for the same cluster, put both private keys into that one Secret.

## Directory tree

1. Go to the `workload-clusters` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    ```

1. Create a new directory with name corresponding to the WC name:

    ```sh
    mkdir ${WC_NAME}
    ```

1. Go to the newly created directory. If you need out-of-band delivery method create also `out-of-band` directory:

    ```sh
    cd ${WC_NAME}
    # mkdir out-of-band       # resources managed outside Management API, created directly in WC
    ```

1. Create 2 sub-directories:

    - `apps` - Workload Cluster managed apps,
    - `cluster` - Workload Cluster definition.

    ```sh
    mkdir apps cluster
    ```

1. Create the `kustomization.yaml` file that lists them. It leaves out `out-of-band`, which must never be applied to
   the Management Cluster:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - apps/
      - cluster/
    EOF
    ```

1. Go to the `apps` directory:

    ```sh
    cd apps
    ```

1. Create the `patch_cluster_config.yaml` file to provide common configuration for all the apps that are going to be
   installed to the new cluster. Here we make sure that every `HelmRelease` knows about the `kubeConfig` secret used to
   connect to the new cluster, so each app only has to describe its own chart and values.

    ```sh
    cat <<EOF > patch_cluster_config.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      labels:
        giantswarm.io/managed-by: flux
      name: ignored
    spec:
      kubeConfig:
        secretRef:
          name: \${cluster_name}-kubeconfig
    EOF
    ```

    **Note**, values are not part of this patch. A patch cannot add a shared entry to `spec.valuesFrom`: `kustomize`
    has no merge strategy for `HelmRelease`, so it falls back to a JSON merge patch, which replaces a list rather than
    appending to it. Instead every `HelmRelease` lists the same layers itself, see
    [bases/apps/hello-world](/bases/apps/hello-world/helm-release.yaml): the `${cluster_name}-cluster-values` ConfigMap
    (`baseDomain`, `provider`, ...) that an App CR used to get from App Platform, the app's defaults, and optional
    `-user-values` / `-user-secrets` overrides. A `HelmRelease` that references a required ConfigMap or Secret which
    does not exist yet stays not-ready and is retried, so there is no race with the order Flux creates objects in.

1. Create the `kustomization.yaml` file, with empty resources (for now) but applying our patch created above to any
   objects we add here in the future:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    patches:
    - path: patch_cluster_config.yaml
      target:
        kind: HelmRelease
    namespace: org-${ORG_NAME}
    resources: []
    EOF
    ```

1. Leave `apps` and go into the `cluster` directory:

    ```sh
    cd ../cluster
    ```

1. Create `kustomization.yaml` file and populate it with empty resources for now. The
   [Workload Cluster instance](./add_wc_instance.md) steps replace it with one that creates the cluster:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    ```

1. Go back to the `workload-clusters` directory and create the cluster's Flux `Kustomization` in the organisation's
   `namespace/workload-clusters` directory. The organisation's namespace `Kustomization` applies it into the
   organisation's namespace, where it runs as that namespace's `automation` ServiceAccount and decrypts with a key
   Secret in the organisation's `namespace/secrets`. It names no namespace, reads the `GitRepository` in `default`,
   and has the organisation's namespace `Kustomization` in `dependsOn`, so that one applies every commit first. Its
   `organization` is `${organization}`, which the organisation's namespace `Kustomization` fills in: the `\$` keeps it
   as it is in the file. With `prune: true`, Flux deletes what you delete from the cluster's files, but not the
   cluster, if its `HelmRelease` has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the
   `giantswarm.io/prevent-deletion` label, as in the cluster bases of this repository. See
   [How it works](./how-it-works.md) and [Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations).
   Use one of the templates:

    - if you haven't created a dedicated GPG key for the cluster (running without Secrets encryption):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../
      mkdir -p ../namespace/workload-clusters
      cat <<EOF > ../namespace/workload-clusters/${WC_NAME}.yaml
      apiVersion: kustomize.toolkit.fluxcd.io/v1
      kind: Kustomization
      metadata:
        name: ${MC_NAME}-clusters-${WC_NAME}
      spec:
        dependsOn:
          - name: ${MC_NAME}-organization-${ORG_NAME}
            namespace: default
        interval: 10m
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}"
        postBuild:
          substitute:
            cluster_name: "${WC_NAME}"
            organization: "\${organization}"
        prune: true
        retryInterval: 1m
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: ${GIT_REPOSITORY_NAME}
          namespace: default
        timeout: 2m
      EOF
      ```

    - if you have created a dedicated GPG key for the cluster (running with Secrets encryption; for an age key,
      name `sops-age-${WC_NAME}` instead):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../
      mkdir -p ../namespace/workload-clusters
      cat <<EOF > ../namespace/workload-clusters/${WC_NAME}.yaml
      apiVersion: kustomize.toolkit.fluxcd.io/v1
      kind: Kustomization
      metadata:
        name: ${MC_NAME}-clusters-${WC_NAME}
      spec:
        decryption:
          provider: sops
          secretRef:
            name: sops-gpg-${WC_NAME}
        dependsOn:
          - name: ${MC_NAME}-organization-${ORG_NAME}
            namespace: default
        interval: 10m
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}"
        postBuild:
          substitute:
            cluster_name: "${WC_NAME}"
            organization: "\${organization}"
        prune: true
        retryInterval: 1m
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: ${GIT_REPOSITORY_NAME}
          namespace: default
        timeout: 2m
      EOF
      ```

   If the cluster's `Kustomization` waits for the cluster with a `Cluster` health check, as
   [WC_NAME.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/namespace/workload-clusters/WC_NAME.yaml) does,
   write the health check's namespace as `org-${organization}`, which the organisation's namespace `Kustomization`
   fills in too.

1. If you use the `out-of-band` delivery method create another Kustomization CR pointing to `out-of-band`
   directory and referencing the right `kubeconfig` Secret. It lives in the namespace of that Secret, which is the
   organization namespace for CAPI clusters, so it goes in the organisation's `namespace/workload-clusters`
   directory: the organisation's namespace `Kustomization` applies it there, and fills in `${organization}`. It names
   no namespace, and depends on the organisation's namespace `Kustomization`, as the cluster's does:

   ```sh
   cat <<EOF > ../namespace/workload-clusters/${WC_NAME}-direct.yaml
   apiVersion: kustomize.toolkit.fluxcd.io/v1
   kind: Kustomization
   metadata:
     name: ${MC_NAME}-clusters-${WC_NAME}-direct
   spec:
     dependsOn:
       - name: ${MC_NAME}-organization-${ORG_NAME}
         namespace: default
     interval: 10m
     kubeConfig:
       secretRef:
         # key: kubeConfig
         name: ${WC_NAME}-kubeconfig
     path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/out-of-band"
     postBuild:
       substitute:
         cluster_name: "${WC_NAME}"
         organization: "\${organization}"
     prune: true
     retryInterval: 1m
     sourceRef:
       kind: GitRepository
       name: ${GIT_REPOSITORY_NAME}
       namespace: default
     timeout: 2m
   EOF
   ```

   **NOTE**: In some cases, especially for the legacy clusters, you may be forced to uncomment the `key` field
   in the above command to tell Flux where to look for the `kubeconfig`. A legacy cluster's `kubeconfig` Secret
   lives in `default`: write the file in `workload-clusters` instead, with `namespace: default`,
   `organization: "ORG_NAME"` and no `dependsOn`, list it in a `kustomization.yaml` there, and list `workload-clusters`
   in the organisation's `kustomization.yaml`, so the management cluster's `Kustomization` applies it.

### Configuring default apps

The default apps of a cluster are part of its cluster chart. Configure them in the cluster values under
`global.apps`, the same way as the rest of the cluster configuration, see
[Add Workload Cluster instance](./add_wc_instance.md).

## MC configuration

1. Still in the `workload-clusters` directory, list the cluster's `Kustomization`, and the out-of-band one if you
   created it, in `namespace/workload-clusters/kustomization.yaml`, and list `workload-clusters` in
   `namespace/kustomization.yaml` if it isn't there yet:

    ```sh
    touch ../namespace/workload-clusters/kustomization.yaml
    yq -i eval ".resources += \"${WC_NAME}.yaml\" | .resources style=\"\"" \
      ../namespace/workload-clusters/kustomization.yaml
    # yq -i eval ".resources += \"${WC_NAME}-direct.yaml\" | .resources style=\"\"" \
    #   ../namespace/workload-clusters/kustomization.yaml
    yq -i eval '.resources |= ((. // []) + ["workload-clusters"] | unique)' ../namespace/kustomization.yaml
    ```

    The resulting file should look like this:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${WC_NAME}.yaml
    ```

After completing all the steps, you can open a PR with the changes. Once it is merged, Flux should be ready to reconcile
the new workload cluster and apps.

## Recommended next steps

- [Add Workload Cluster instance](./add_wc_instance.md)
- [Managing Apps installed in clusters with GitOps](./guides/README.md)
