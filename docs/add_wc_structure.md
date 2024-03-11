# Add a new Workload Cluster repository structure

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Create Flux GPG regular key pair (optional step)](#create-flux-gpg-regular-key-pair-optional-step)
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

*Note: As always, instructions here respect the [repository structure](./repo_structure.md).*

## Example

An example of a WC cluster directory structure is available in [WC_NAME/](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/).

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

1. Configure automatic key selection rule in the [SOPS configuration file](/.sops.yaml):

    ```sh
    cat <<EOF >> .sops.yaml
      - encrypted_regex: ^(data|stringData)$
        path_regex: management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/.*\.enc\.yaml
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

1. Go to the newly created directory and create `mapi` directory. If you need out-of-band
   delivery method create also `out-of-band` directory. Next go to the `mapi` directory:

    ```sh
    mkdir mapi                # resources managed with Management API
    # mkdir out-of-band       # resources managed outside Management API, created directly in WC
    cd mapi
    ```

1. Create 2 sub-directories:

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
          name: ${cluster_name}-cluster-values
          namespace: ${cluster_name}
      kubeConfig:
        context:
          name: giantswarm-${cluster_name}-context
        inCluster: false
        secret:
          name: ${cluster_name}-kubeconfig
          namespace: ${cluster_name}
    EOF
    ```

    **Note**, the `giantswarm.io/managed-by: flux` label is very important here, it tells the `app-admission-controller`
    of App Platform to ignore any missing ConfigMaps and Secrets set in `spec.userConfig` of the App CRs. This is needed
    to avoid race conditions, where Flux creates first the App CR and only later a referenced ConfigMap or Secret.

1. Create the `kustomization.yaml` file, with empty resources (for now) but applying our patch created above to any
   objects we add here in the future:

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

1. Go back to the `workload-clusters` directory and create Kustomization CR for it. Use one of the templates:

    - if you haven't created a dedicated GPG key for the cluster (running without Secrets encryption):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../../
      cat <<EOF > ${WC_NAME}.yaml
      apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
      kind: Kustomization
      metadata:
        name: ${MC_NAME}-clusters-${WC_NAME}
        namespace: default
      spec:
        interval: 1m
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi"
        postBuild:
          substitute:
            cluster_name: "${WC_NAME}"
        prune: false
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: ${GIT_REPOSITORY_NAME}
        timeout: 2m
      ```

    - if you have created a dedicated GPG key for the cluster (running with Secrets encryption):

      ```sh
      # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
      cd ../../../
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
        path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi"
        postBuild:
          substitute:
            cluster_name: "${WC_NAME}"
        prune: false
        serviceAccountName: automation
        sourceRef:
          kind: GitRepository
          name: ${GIT_REPOSITORY_NAME}
        timeout: 2m
      ```

1. If you use the `out-of-band` delivery method create another Kustomization CR pointing to `out-of-band`
   directory and referencing the right `kubeconfig` file:

   ```sh
   cat <<EOF >> ${WC_NAME}-direct.yaml
   ---
   apiVersion: kustomize.toolkit.fluxcd.io/v1beta2
   kind: Kustomization
   metadata:
     name: ${MC_NAME}-clusters-${WC_NAME}-direct
     namespace: ${WC_NAME}
   spec:
     interval: 1m
     kubeConfig:
       secretRef:
         # key: kubeConfig
         name: ${WC_NAME}-kubeconfig
     path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/out-of-band"
     prune: false
     sourceRef:
       kind: GitRepository
       name: ${GIT_REPOSITORY_NAME}
       namespace: default
     timeout: 2m
   EOF
   ```

   **NOTE**: In some cases, especially for the legacy clusters, you may be forced to uncomment the `key` field
   in the above command to tell Flux where to look for the `kubeconfig`.

### Configuring default-apps

You can also kustomize the `default-apps` for your cluster by creating a [user config map](https://docs.giantswarm.io/app-platform/app-configuration/)
and patching the CR for the App.

1. Create the user config map in the workload cluster's `cluster` directory. For example, let's configure CoreDNS:

   ```sh
   # management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/mapi/cluster
   cd ${WC_NAME}/mapi/cluster
   echo <<EOF >> default_apps_user_config.yaml
   apiVersion: v1
   data:
     values: |
       userConfig:
         coreDNS:
           configMap:
              values: |
                configmap:
                  custom:
                    my-domain.local {
                      log
                      errors
                      cache 30
                      loop
                      reload
                      loadbalance
                  }
   kind: ConfigMap
   metadata:
   name: ${cluster_name}-default-apps-userconfig
   namespace: org-${organization}
   EOF
   ```

1. Create the patch for the `default-apps` CR:

    ```sh
    echo <<EOF >> patch_user_config_default_apps.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: ${cluster_name}-default-apps
      namespace: org-${organization}
    spec:
      userConfig:
        configMap:
          name: ${cluster_name}-default-apps-userconfig
          namespace: org-${organization}
    EOF
    ```

1. Finally, add the user config map and the patch to the `${WC_NAME}/mapi/cluster/kustomization.yaml`

   ```sh
   yq -i eval ".patchesStrategicMerge += \"default_apps_user_config.yaml\" | .patchesStrategicMerge style=\"\"" kustomization.yaml
   yq -i eval ".resources += \"patch_user_config_default_apps.yaml\" | .resources style=\"\"" kustomization.yaml
   ```

## MC configuration

1. Go to the `workload-clusters` directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
    ```

1. Edit the mandatory `kustomization.yaml` adding the WC's Kustomization CR as a resource. Uncomment second
   line if you have created the out-of-band Kustomization CR as well:

    ```sh
    yq -i eval ".resources += \"${WC_NAME}.yaml\" | .resources style=\"\"" kustomization.yaml
    # yq -i eval ".resources += \"${WC_NAME}-direct.yaml\" | .resources style=\"\"" kustomization.yaml
    ```

    The resulting file should look like this:

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${WC_NAME}.yaml
    - ${WC_NAME}-direct.yaml
    ```

After completing all the steps, you can open a PR with the changes. Once it is merged, Flux should be ready to reconcile
the new workload cluster and apps.

## Recommended next steps

- [Add Workload Cluster instance](./add_wc_instance.md)
- [Managing Apps installed in clusters with GitOps](./apps/README.md)
