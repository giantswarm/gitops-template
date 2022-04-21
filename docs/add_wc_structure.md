# Add a new Workload Cluster repository structure

Adding a new Workload Cluster requires a few major steps in the configuration process. One of them
is to prepare the necessary structure and configuration for the GitOps repository itself.

This includes:

1. [Preparing a new, cluster-specific, Secrets encryption GPG key](#create-flux-gpg-regular-key-pair-optional-step).
1. [Preparing directory tree](#directory-tree) - which shows files, directories and their layout that are needed to complete
   our configuration.
1. [Adding our new Workload Cluster to an existing Management Cluster definition](#mc-configuration).

*Note: As always, instructions here respect the [repository structure](./repo_structure.md).*

## Example

An example of a WC cluster directory structure is available in [WC_NAME/](../management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/).

## Export environment variables

**Note**, Management Cluster codename, Organization name and Workload Cluster name are needed in multiple places across
this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
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
    Key-Type: 1
    Key-Length: 4096
    Subkey-Type: 1
    Subkey-Length: 4096
    Expire-Date: 0
    Name-Comment: ${KEY_COMMENT}
    Name-Real: ${KEY_NAME}
    EOF
    ```

1. Retrieve the key fingerprint and store it in an environment variable:

    ```sh
    gpg --list-secret-keys "${KEY_NAME}"

    sec   rsa4096 2021-11-25 [SC]
          YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY

    export KEY_FP=YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY
    ```

1. Save the private key as a Kubernetes Secret into the MC `secrets` directory:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-${WC_NAME} \
    --dry-run=client \
    --namespace=default \
    --from-file=${WC_NAME}.main.asc=/dev/stdin \
    -o yaml > management-clusters/${MC_NAME}/secrets/${WC_NAME}.gpgkey.enc.yaml
    ```

1. Edit the `management-clusters/${MC_NAME}/secrets/kustomization.yaml` by adding the newly created secret to its resources:

    ```yaml
    resources:
    - ${WC_NAME}.gpgkey.enc.yaml
    ```

1. Import the master GPG public key and encrypt the Kubernetes Secret with it:

    ```sh
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
    sops --encrypt --in-place management-clusters/${MC_NAME}/secrets/${WC_NAME}.gpgkey.enc.yaml
    ```

1. As a backup, save the private key to an external encrypted storage. As an example, you can add the private key
   to LastPass as a secure note:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    lpass add --notes --non-interactive "Shared-Dev Common/GPG private key (${MC_NAME}, ${WC_NAME}, Flux)"
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

1. Configure automatic key selection rule in the [SOPS configuration file](../.sops.yaml):

    ```sh
    cat <<EOF >> .sops.yaml
      - path_regex: management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/.*\.enc\.yaml
        encrypted_regex: ^(data|stringData)$
        pgp: ${KEY_FP}
    EOF
    ```

## Directory tree

1. Go to the `workload-clusters` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    ```

1. Create a new directory with name corresponding to the WC name:

    ```sh
    mkdir ${WC_NAME}
    ```

1. Go to the newly created directory and create 2 sub-directories there:

    - `apps` - Workload Cluster managed apps,
    - `cluster` - Workload Cluster definition.

    ```sh
    cd ${WC_NAME}
    mkdir apps cluster
    ```

1. Go to the `apps` directory:

    ```sh
    cd apps
    ```

1. Create the `patch_cluster_config.yaml` file to provide common configuration for all the Apps that are going to be
   installed to the new cluster. We're basically ensuring 2 things here: first, that there's a shared Config Map that we
   will use for common values (like cluster's domain name), and second that all the apps know how to configure a
   `kubeConfig` secret that will be used to connect to the new cluster.

    ```sh
    cat <<EOF > patch_cluster_config.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      labels:
        giantswarm.io/managed-by: flux
      name: ignored
    spec:
      config:
        configMap:
          name: ${cluster_id}-cluster-values
          namespace: ${cluster_id}
      kubeConfig:
        context:
          name: giantswarm-${cluster_id}-context
        inCluster: false
        secret:
          name: ${cluster_id}-kubeconfig
          namespace: ${cluster_id}
    EOF
    ```

    **Note**, the `giantswarm.io/managed-by: flux` label is very important here, it tells the `app-admission-controller`
    of App Platform to ignore any missing ConfigMaps and Secrets set in `spec.userConfig` of the App CRs. This is needed
    to avoid race conditions, where Flux creates first the App CR and only later a referenced ConfigMap or Secret.

1. Create the `kustomization.yaml` file, with empty resources (for now) but applying our patch created above to any
   objects we add here in future:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    patches:
    - path: patch_cluster_config.yaml
      target:
        kind: App
    - patch: |-
        - op: replace
          path: "/metadata/namespace"
          value: ${WC_NAME}
      target:
        kind: ".*"
    resources: []
    EOF
    ```

1. Leave `apps` and go into the `cluster` directory:

    ```sh
    cd ../cluster
    ```

1. Create `kustomization.yaml` file and populate it with empty resources for now:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    ```

1. Go back to the `workload-clusters` directory and create Kustomization CR for it. Use one fo the templates:

    - if you haven't created a dedicated GPG key for the cluster (running without Secrets encryption):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../
      cat <<EOF > ${WC_NAME}.yaml
      apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
      kind: Kustomization
      metadata:
        name: ${MC_NAME}-clusters-${WC_NAME}
        namespace: default
      spec:
        interval: 1m
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}"
        postBuild:
          substitute:
            cluster_id: "${WC_NAME}"
        prune: false
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: YOUR_REPO
        timeout: 2m
      EOF
      ```

    - if you have created a dedicated GPG key for the cluster (running with Secrets encryption):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../
      cat <<EOF > ${WC_NAME}.yaml
      apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
      kind: Kustomization
      metadata:
        name: ${MC_NAME}-clusters-${WC_NAME}
        namespace: default
      spec:
        decryption:
          provider: sops
          secretRef:
            name: sops-gpg-${WC_NAME}
        interval: 1m
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}"
        postBuild:
          substitute:
            cluster_id: "${WC_NAME}"
        prune: false
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: YOUR_REPO
        timeout: 2m
      EOF
      ```

## MC configuration

1. Go to the `workload-clusters` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    ```

1. Edit the mandatory `kustomization.yaml` adding the WC's Kustomization CR as a resource:

    ```sh
    yq -i e ".resources += \"${WC_NAME}.yaml\" | .resources style=\"\"" kustomization.yaml
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

- [add Workload Cluster instance](./add_wc_instance.md)
- [add a new App CR to the Workload Cluster](./add_appcr.md)
