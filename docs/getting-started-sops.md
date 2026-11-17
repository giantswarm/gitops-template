# Getting started with SOPS

This guide takes you from a fork of this repository to a running workload cluster with an app, all managed by Flux.
You connect your management cluster to the repository, add an organization, create a workload cluster, then deploy
and update an app.

Every change goes the same way: you commit a file, push it, and Flux on the management cluster applies it. To learn
more about the approach, see
[GitOps at Giant Swarm](https://docs.giantswarm.io/tutorials/continuous-deployment/gitops-at-giantswarm/).

Secrets are stored in the repository, encrypted with [SOPS](https://github.com/getsops/sops) and a GPG key that
only Flux on the management cluster holds. If you'd rather keep secrets out of the repository, in a secret manager,
follow [Getting started](./getting-started.md) instead.

- [Before you start](#before-you-start)
- [1. Connect the management cluster](#1-connect-the-management-cluster)
- [2. Add an organization](#2-add-an-organization)
- [3. Create a workload cluster](#3-create-a-workload-cluster)
- [4. Deploy an app](#4-deploy-an-app)
- [5. Update the app](#5-update-the-app)
- [6. Delete the cluster (optional)](#6-delete-the-cluster-optional)
- [Next steps](#next-steps)

## Before you start

You need:

- the tools listed in [Appendices](./appendices.md): `git`, `kubectl`,
  [`kubectl gs`](https://docs.giantswarm.io/reference/kubectl-gs/) 6.0.0 or newer, see
  [kubectl-gs version](./appendices.md#kubectl-gs-version), `flux`, `gpg`, `sops` and `yq`,
- access to the management cluster, see
  [Access to the platform API](https://docs.giantswarm.io/getting-started/access-to-platform-api/). Log in with
  `kubectl gs login API_URL`, where `API_URL` is the management cluster's Kubernetes API URL. After that, the context
  is named `gs-MC_NAME`. You need write access to the `default` and `org-*` namespaces,
- a fork of this repository, cloned locally. Run all commands from the root of the clone.

The fork comes with example directories named `MC_NAME`, `ORG_NAME`, `WC_NAME` and so on. Flux ignores them, so you
can keep them for reference.

Export the names used in all the commands below:

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export ORG_NAME=ORGANIZATION         # organization name, without the `org-` prefix
export WC_NAME=CLUSTER_NAME          # name of the new workload cluster, lowercase letters and digits, at most 20 characters
export GITOPS_REPO=REPO_NAME         # name for the Flux GitRepository, for example `gitops`
export GITOPS_REPO_URL=https://github.com/YOUR_ORG/YOUR_REPO

export MC_DIR=management-clusters/${MC_NAME}
export ORG_DIR=${MC_DIR}/organizations/${ORG_NAME}
export WC_DIR=${ORG_DIR}/workload-clusters/${WC_NAME}
```

Note that the variables only live in your current shell. If you open a new one, run the exports again.

## 1. Connect the management cluster

Flux on the management cluster needs three things: a key to decrypt secrets stored in the repository, access to the
repository, and a `Kustomization` that tells it which directory to apply.

> **Shortcut:** [`kubectl gs gitops add management-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-mc/)
> does steps 1 to 6 for you, with a new master key:
>
> ```sh
> kubectl gs gitops add management-cluster --name ${MC_NAME} --repository-name ${GITOPS_REPO} --gen-master-key
> ```
>
> It doesn't add the key to your GPG keyring. Import it from the Secret file it created:
>
> ```sh
> yq '.data[]' ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml | base64 -d | gpg --import
> ```
>
> The `Kustomization` it writes has `prune: false`. Set `prune: true`, as in step 2:
>
> ```sh
> yq -i '.spec.prune = true' ${MC_DIR}/${MC_NAME}.yaml
> ```
>
> Then set `KEY_FP` as in step 4, and continue with step 7.

1. Create the management cluster's directory:

    ```sh
    mkdir -p ${MC_DIR}/.sops.keys ${MC_DIR}/secrets ${MC_DIR}/organizations
    ```

1. Create the `Kustomization` that applies the management cluster directory:

    ```sh
    cat <<EOF > ${MC_DIR}/${MC_NAME}.yaml
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
      interval: 1m
      path: ./management-clusters/${MC_NAME}
      prune: true
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
      timeout: 2m
    EOF
    ```

1. (Optional) Create a GPG master key without a passphrase. If you already have a master key for this management
   cluster, skip this command. Save the private key from your password manager to a file and import it instead, with
   `gpg --import FILE`:

    ```sh
    gpg --batch --full-generate-key <<EOF
    %no-protection
    Key-Type: EDDSA
    Key-Curve: ed25519
    Key-Usage: sign
    Subkey-Type: ECDH
    Subkey-Curve: cv25519
    Subkey-Usage: encrypt
    Expire-Date: 0
    Name-Comment: ${MC_NAME} Flux Master
    Name-Real: ${MC_NAME}
    EOF
    ```

1. Save the key's fingerprint for the next commands:

    ```sh
    export KEY_FP=$(gpg --list-secret-keys --with-colons "${MC_NAME} Flux Master" | awk -F: '/^fpr/{print $10; exit}')
    ```

    If you imported a key with another name, set `KEY_FP` to the fingerprint that `gpg --list-secret-keys` shows.

1. Write the private key into the `sops-gpg-master` Secret:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-master --namespace=default \
    --from-file=${MC_NAME}.master.asc=/dev/stdin --dry-run=client -o yaml \
    > ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Share the public key in the repository:

    ```sh
    gpg --export --armor "${KEY_FP}" > ${MC_DIR}/.sops.keys/.sops.master.asc
    ```

    Add a rule to `.sops.yaml`, so `sops` encrypts the files in the `secrets` directory with this key:

    ```sh
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/secrets/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }]' .sops.yaml
    ```

1. Apply the Secret, so Flux can decrypt files with the key. If the management cluster already has this key in its
   `sops-gpg-master` Secret, this command changes nothing:

    ```sh
    kubectl apply -f ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

1. Encrypt the Secret, which keeps an encrypted copy of the key in the repository:

    ```sh
    sops --encrypt --in-place ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml
    ```

    List it in the `secrets` directory's `kustomization.yaml`:

    ```sh
    cat <<EOF > ${MC_DIR}/secrets/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
    - ${MC_NAME}.gpgkey.enc.yaml
    EOF
    ```

1. (Optional) Print the private key and store it in your password manager. You need it to add more keys later. Skip
   this if the key is already in your password manager:

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}"
    ```

    Then remove it from your machine:

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

1. Commit and push:

    ```sh
    git add .sops.yaml ${MC_DIR} && git commit -m "Add management cluster ${MC_NAME}" && git push
    ```

1. Connect Flux to the repository. (Optional) Store a GitHub token in a Secret. Skip this if the
   `github-https-credentials` Secret already exists in the `default` namespace and can read this repository. The token
   needs read access to the repository's contents, for example a
   [fine-grained personal access token][github-token]:

    ```sh
    flux create secret git github-https-credentials --namespace=default \
    --url=${GITOPS_REPO_URL} --username=git --password=YOUR_GITHUB_TOKEN
    ```

    Create the `GitRepository`. Its `ignore` field keeps Flux from reading the example directories:

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

    Finally, apply the `Kustomization`:

    ```sh
    kubectl apply -f ${MC_DIR}/${MC_NAME}.yaml
    ```

    These are the only resources you apply by hand. From now on, Flux applies everything you push.

**Check:** the `GitRepository` is `Ready`:

```sh
flux get sources git ${GITOPS_REPO} -n default
```

The `Kustomization` is `Ready` too:

```sh
flux get kustomizations ${MC_NAME}-gitops -n default
```

## 2. Add an organization

An organization groups clusters and owns the `org-${ORG_NAME}` namespace they live in. If the organization already
exists, these steps bring it under GitOps.

> **Shortcut:** [`kubectl gs gitops add organization`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-org/)
> creates the same files, but without the annotation of the `Organization` below:
>
> ```sh
> kubectl gs gitops add organization --name ${ORG_NAME} --management-cluster ${MC_NAME}
> ```
>
> Add it:
>
> ```sh
> yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled"' ${ORG_DIR}/${ORG_NAME}.yaml
> ```

First, create the organization's directory:

```sh
mkdir -p ${ORG_DIR}/workload-clusters
```

Create the `Organization`. Deleting it deletes the `org-${ORG_NAME}` namespace, with every cluster in it, so the
annotation keeps Flux from deleting it when its file is deleted:

```sh
cat <<EOF > ${ORG_DIR}/${ORG_NAME}.yaml
apiVersion: security.giantswarm.io/v1alpha1
kind: Organization
metadata:
  annotations:
    kustomize.toolkit.fluxcd.io/prune: disabled
  name: ${ORG_NAME}
spec: {}
EOF
```

Create an empty list of clusters. You add your cluster to it in the next step:

```sh
cat <<EOF > ${ORG_DIR}/workload-clusters/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
EOF
```

Finally, commit and push:

```sh
git add ${ORG_DIR} && git commit -m "Add organization ${ORG_NAME}" && git push
```

**Check:** the namespace `org-${ORG_NAME}` exists, which takes about a minute:

```sh
kubectl get namespace org-${ORG_NAME}
```

## 3. Create a workload cluster

A cluster gets its own `Kustomization`, which applies the `${WC_DIR}/mapi` directory and fills in variables such as
`${cluster_name}` in the files below. The cluster itself is a Flux `HelmRelease` that installs the `release-aws` chart,
built from the [CAPA cluster base](/bases/clusters/capa/template) that ships with this repository. The chart version is
the Giant Swarm release, so the release the cluster runs is stored in Git. `release-aws` rejects a cluster name longer
than 20 characters. For other providers, see [Add a CAPx Workload Cluster template](./guides/cluster-templates.md).

> **Shortcut:** [`kubectl gs gitops add workload-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-wc/)
> creates the same cluster, with the same file and resource names. After you pick a release in the first step below,
> run:
>
> ```sh
> kubectl gs gitops add workload-cluster --name ${WC_NAME} --organization ${ORG_NAME} \
>   --management-cluster ${MC_NAME} --repository-name ${GITOPS_REPO} \
>   --base bases/clusters/capa/template --release ${RELEASE_VERSION}
> ```
>
> The CLI doesn't add a region, so add it to the cluster's `kustomization.yaml`, with the `REGION` from the second step
> below:
>
> ```sh
> yq -i '.components = ["../../../../../../../../bases/environments/regions/" + strenv(REGION)]' \
>   ${WC_DIR}/mapi/cluster/kustomization.yaml
> ```
>
> The cluster's `Kustomization` it writes has `prune: false`. Set `prune: true`, as below:
>
> ```sh
> yq -i '.spec.prune = true' ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml
> ```
>
> Then commit and push, as in the last step below.

1. List the Giant Swarm releases and pick an AWS one from v34.0.0 on. These have a `release-aws` chart:

    ```sh
    kubectl get releases.release.giantswarm.io
    ```

    Export the release you picked, without the `aws-` prefix:

    ```sh
    export RELEASE_VERSION=36.2.0
    ```

1. Pick the cluster's region from [bases/environments/regions](/bases/environments/regions). Every cluster needs
   one: without it, the chart creates the cluster in the region of the management cluster's nodes, and
   `tools/validate-helm-values` fails. To add a region, see [Regions](./guides/environments.md#regions).

    ```sh
    export REGION=eu_central
    ```

1. Create the cluster definition. It points at the CAPA cluster base and adds the region as a component. First, create
   its directory:

    ```sh
    mkdir -p ${WC_DIR}/mapi/cluster
    ```

    Then create its `kustomization.yaml`:

    ```sh
    cat <<EOF > ${WC_DIR}/mapi/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    components:
      - ../../../../../../../../bases/environments/regions/${REGION}
    resources:
      - ../../../../../../../../bases/clusters/capa/template
    EOF
    ```

    The cluster runs with the base's defaults. To add your own values, see
    [Creating a cluster from the CAPA cluster base](./add_wc_instance.md#creating-a-cluster-from-the-capa-cluster-base).
    Don't set `global.release.version` in them, because the chart sets it.

1. Create the list of apps to deploy to the cluster. It starts empty, and you add an app to it in the next step. First,
   create its directory:

    ```sh
    mkdir -p ${WC_DIR}/mapi/apps
    ```

    Then create the list:

    ```sh
    cat <<'EOF' > ${WC_DIR}/mapi/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    buildMetadata: [originAnnotations]
    namespace: org-${organization}
    resources: []
    EOF
    ```

1. Create the cluster's `Kustomization`. With `prune: true`, Flux deletes what you delete from the cluster's files.
   It never deletes the cluster itself: the cluster's `HelmRelease`, from the CAPA cluster base, has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${WC_NAME}
      namespace: default
    spec:
      interval: 1m
      path: ./${WC_DIR}/mapi
      postBuild:
        substitute:
          cluster_description: "${WC_NAME} managed by GitOps"
          cluster_name: "${WC_NAME}"
          organization: "${ORG_NAME}"
          release: "${RELEASE_VERSION}"
      prune: true
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
      timeout: 2m
    EOF
    ```

    Add it to the organization's list of clusters:

    ```sh
    yq -i '.resources += ["'"${WC_NAME}"'.yaml"]' ${ORG_DIR}/workload-clusters/kustomization.yaml
    ```

    Finally, commit and push:

    ```sh
    git add ${ORG_DIR} && git commit -m "Add workload cluster ${WC_NAME}" && git push
    ```

**Check:** the cluster's `Kustomization` is `Ready`:

```sh
flux get kustomizations ${MC_NAME}-clusters-${WC_NAME} -n default
```

The cluster takes 15 to 20 minutes to come up. Watch it with:

```sh
kubectl gs get clusters -n org-${ORG_NAME}
```

Once the cluster is up, log in to it:

```sh
kubectl gs login ${MC_NAME} --workload-cluster ${WC_NAME} --organization ${ORG_NAME}
```

Save its context for the checks below:

```sh
export WC_CONTEXT=$(kubectl config current-context)
```

Then switch back to the management cluster:

```sh
kubectl config use-context gs-${MC_NAME}
```

Learn more:
[Managing workload clusters with GitOps](https://docs.giantswarm.io/tutorials/continuous-deployment/manage-workload-clusters/).

## 4. Deploy an app

An app is two Flux resources on the management cluster: an `OCIRepository` that points at a Helm chart, and a
`HelmRelease` that installs it into the workload cluster through the cluster's `${cluster_name}-kubeconfig` Secret.
Here you deploy the [hello-world](https://github.com/giantswarm/hello-world-app) chart.

> **Shortcut:** [`kubectl gs deploy chart`](https://docs.giantswarm.io/reference/kubectl-gs/deploy-chart/) with
> `--dry-run` writes the `OCIRepository` and the `HelmRelease` for you. It checks that the chart version exists, then
> prints the resources instead of applying them. Always pass `--dry-run` here. Without it, the command applies the
> resources to the management cluster directly, outside of Git. After the first step below, run:
>
> ```sh
> kubectl gs deploy chart --chart-name hello-world --version 3.2.3 \
>   --organization ${ORG_NAME} --target-cluster ${WC_NAME} --target-namespace hello-world \
>   --values-from ConfigMap/${WC_NAME}-cluster-values:values \
>   --values-from ConfigMap/${WC_NAME}-hello-world-values:values \
>   --dry-run | APP_DIR=${APP_DIR:?run the first step below} \
>   yq -s '.kind as $k | strenv(APP_DIR) + "/" +
>     {"HelmRelease": "helm-release", "OCIRepository": "oci-repository"}[$k] + ".yaml"'
> ```
>
> This writes `oci-repository.yaml` and `helm-release.yaml`. Then continue with the `values.yaml` step.

1. Save the app's directory for the next commands:

    ```sh
    export APP_DIR=${WC_DIR}/mapi/apps/hello-world
    ```

    Then create it:

    ```sh
    mkdir -p ${APP_DIR}
    ```

1. Create the `OCIRepository`, which sets the chart and its version:

    ```sh
    cat <<'EOF' > ${APP_DIR}/oci-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}-hello-world
      namespace: org-${organization}
    spec:
      interval: 10m
      ref:
        tag: 3.2.3
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
    EOF
    ```

1. Create the `HelmRelease`, which installs the chart into the workload cluster:

    ```sh
    cat <<'EOF' > ${APP_DIR}/helm-release.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      name: ${cluster_name}-hello-world
      namespace: org-${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: ${cluster_name}-hello-world
      install:
        createNamespace: true
      interval: 5m
      kubeConfig:
        secretRef:
          name: ${cluster_name}-kubeconfig
      releaseName: hello-world
      storageNamespace: hello-world
      targetNamespace: hello-world
      valuesFrom:
        - kind: ConfigMap
          name: ${cluster_name}-cluster-values
          valuesKey: values
        - kind: ConfigMap
          name: ${cluster_name}-hello-world-values
          valuesKey: values
    EOF
    ```

    The `${cluster_name}-cluster-values` ConfigMap is created for every workload cluster and gives the chart values
    such as `baseDomain`. Values listed later in `valuesFrom` win.

1. Put the app's values into `values.yaml`:

    ```sh
    cat <<'EOF' > ${APP_DIR}/values.yaml
    ingress:
      enabled: false
    EOF
    ```

1. Create the `kustomization.yaml`. Its `configMapGenerator` turns `values.yaml` into the ConfigMap the `HelmRelease`
   reads:

    ```sh
    cat <<'EOF' > ${APP_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: org-${organization}
    configMapGenerator:
      - name: ${cluster_name}-hello-world-values
        files:
          - values=values.yaml
    generatorOptions:
      disableNameSuffixHash: true
    resources:
      - oci-repository.yaml
      - helm-release.yaml
    EOF
    ```

1. Add the app to the cluster's list of apps:

    ```sh
    yq -i '.resources += ["hello-world"]' ${WC_DIR}/mapi/apps/kustomization.yaml
    ```

1. Commit and push:

    ```sh
    git add ${WC_DIR}/mapi/apps && git commit -m "Deploy hello-world to ${WC_NAME}" && git push
    ```

**Check:** the release is `Ready` on the management cluster:

```sh
flux get helmreleases ${WC_NAME}-hello-world -n org-${ORG_NAME}
```

The pods run in the workload cluster:

```sh
kubectl --context ${WC_CONTEXT} get pods -n hello-world
```

Learn more:
[Deploying an app with a Flux HelmRelease](https://docs.giantswarm.io/tutorials/fleet-management/app-platform/deploy-app-helmrelease/).

## 5. Update the app

To update an app, change its files and push. First, upgrade the chart:

```sh
yq -i '.spec.ref.tag = "3.2.4"' ${APP_DIR}/oci-repository.yaml
```

Next, change a value so that at least two replicas run:

```sh
yq -i '.autoscaling.minReplicas = 2' ${APP_DIR}/values.yaml
```

Then commit and push:

```sh
git add ${APP_DIR} && git commit -m "Update hello-world on ${WC_NAME}" && git push
```

**Check:** the release reports the new chart version:

```sh
flux get helmreleases ${WC_NAME}-hello-world -n org-${ORG_NAME}
```

At least two pods run:

```sh
kubectl --context ${WC_CONTEXT} get pods -n hello-world
```

To let Flux install new chart versions by itself, replace `tag` with a `semver` range in the `OCIRepository`. For
example, `semver: 3.2.x` installs every new patch version.

## 6. Delete the cluster (optional)

Skip this step to keep the cluster. When you delete the cluster's files, Flux deletes its `Kustomization`, its apps and
its configuration, but not the cluster: its `HelmRelease` has the `kustomize.toolkit.fluxcd.io/prune: disabled`
annotation, so Flux keeps it. You delete it by hand at the end. See [How it works](./how-it-works.md).

> **Warning:** `kubectl gs` doesn't write the annotation yet. The `Organization` that `kubectl gs gitops add
> organization` writes doesn't have it, nor does the cluster `HelmRelease` of a base that `kubectl gs gitops add base`
> writes. Add it by hand before you rely on Flux to keep them when their files are deleted.

1. Remove the cluster from the organization's list:

    ```sh
    yq -i 'del(.resources[] | select(. == "'"${WC_NAME}"'.yaml"))' ${ORG_DIR}/workload-clusters/kustomization.yaml
    ```

    Remove its files, then commit and push:

    ```sh
    git rm -r ${WC_DIR} ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml && git commit -am "Delete workload cluster ${WC_NAME}" && git push
    ```

1. Make Flux read the change right away:

    ```sh
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    ```

    Flux deletes the cluster's `Kustomization`, which deletes the cluster's apps and configuration first. Wait until
    it's gone:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME} -n default --timeout=10m
    ```

1. Finally, delete the cluster's `HelmRelease`. This deletes the cluster:

    ```sh
    kubectl delete helmrelease ${WC_NAME} -n org-${ORG_NAME}
    ```

## Next steps

- Keep secrets in a secret manager instead, with External Secrets Operator: [Getting started](./getting-started.md).
- Keep secrets in the repository, encrypted with SOPS: create a
  [key for the cluster](./add_wc_structure.md#create-flux-gpg-regular-key-pair-optional-step), then
  [provide encrypted values](./guides/add-app.md#providing-encrypted-values).
- Reuse an app's configuration across clusters: [App Templates](./guides/app-templates.md) and
  [App Sets](./guides/app-sets.md).
- Run dev, staging and production clusters from shared templates:
  [Add Workload Cluster environments](./guides/environments.md).
- Understand how the repository is organized: [Repository structure](./reference/repo-structure.md).
- See which key decrypts which files: [SOPS keys](./reference/sops-keys.md).

[github-token]: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token
