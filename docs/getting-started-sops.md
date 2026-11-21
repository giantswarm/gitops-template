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
> Then set `KEY_FP` as in step 4. The CLI adds the `.sops.yaml` rule for the `secrets` directory only: add the second
> rule of step 6, for the workload clusters' keys, and continue with step 7.

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
      interval: 10m
      path: ./management-clusters/${MC_NAME}
      prune: true
      retryInterval: 1m
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

    Add rules to `.sops.yaml`, so `sops` encrypts the files in the `secrets` directory with this key, and the workload
    clusters' SOPS keys, which go in their organisation's `namespace/secrets`, see
    [SOPS keys](./reference/sops-keys.md#encryption-rules):

    ```sh
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/secrets/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }, {
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/[^/]+/namespace/secrets/.*\\.(gpg|age)key\\.enc\\.yaml",
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
    commonAnnotations:
      kustomize.toolkit.fluxcd.io/prune: disabled
    labels:
    - pairs:
        giantswarm.io/prevent-deletion: "true"
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
> creates the same files, but without the annotation of the `Organization` below, and without the organisation's
> namespace `Kustomization` and `kustomization.yaml`, which you create as below:
>
> ```sh
> kubectl gs gitops add organization --name ${ORG_NAME} --management-cluster ${MC_NAME}
> ```
>
> Add the annotation:
>
> ```sh
> yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled"' ${ORG_DIR}/${ORG_NAME}.yaml
> ```
>
> The CLI also writes `${ORG_DIR}/workload-clusters/kustomization.yaml`, a list of clusters that this guide keeps in
> `${ORG_DIR}/namespace/workload-clusters` instead. Keep it if you use the CLI for the cluster in the next step, which
> needs it, and leave it out of the organisation's `kustomization.yaml` below.

First, create the organization's directory, with `namespace` for what the organisation keeps in its namespace, its
clusters' `Kustomization`s among them:

```sh
mkdir -p ${ORG_DIR}/namespace/workload-clusters
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
  labels:
    giantswarm.io/prevent-deletion: "true"
  name: ${ORG_NAME}
spec: {}
EOF
```

Create the organisation's namespace `Kustomization`. Your management cluster's `Kustomization` applies only the
`Organization` and objects in `default`, so it works before organization-operator has created the namespace. This
`Kustomization`, in `default`, applies the organisation's `namespace` directory into `org-${ORG_NAME}`: it fails until
the namespace exists and succeeds on its next retry. Its `dependsOn` names your management cluster's `Kustomization`,
so that one always applies a commit first. `ORG_NAME` and `org-ORG_NAME` are placeholders that the
organisation's `kustomization.yaml` completes, see
[Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations). The `namespace` directory lists only the
organisation's list of clusters, which is empty. You add your cluster to it in the next step:

```sh
cat <<EOF > ${ORG_DIR}/namespace.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  labels:
    giantswarm.io/organization-namespace: "true"
  name: ${MC_NAME}-organization-${ORG_NAME}
  namespace: default
spec:
  dependsOn:
    - name: ${MC_NAME}-gitops
  decryption:
    provider: sops
    secretRef:
      name: sops-gpg-master
  interval: 10m
  path: ./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace
  postBuild:
    substitute:
      organization: "ORG_NAME"
  prune: true
  retryInterval: 1m
  serviceAccountName: automation
  sourceRef:
    kind: GitRepository
    name: ${GITOPS_REPO}
  targetNamespace: org-ORG_NAME
  timeout: 2m
EOF
cat <<EOF > ${ORG_DIR}/namespace/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - workload-clusters
EOF
cat <<EOF > ${ORG_DIR}/namespace/workload-clusters/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: []
EOF
```

Create the organisation's `kustomization.yaml`. Its replacements copy the name of the `Organization` into the
`organization` and the `targetNamespace` of the organisation's namespace `Kustomization`, see
[The organisation's name](./reference/repo-structure.md#the-organisations-name). The quoted `'EOF'` keeps the
placeholders as they are:

```sh
cat <<'EOF' > ${ORG_DIR}/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ORGANIZATION_FILE
  - namespace.yaml
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
          labelSelector: giantswarm.io/organization-namespace=true
        fieldPaths:
          - spec.targetNamespace
        options:
          delimiter: "-"
          index: 1
EOF
yq -i '.resources[0] = "'"${ORG_NAME}"'.yaml"' ${ORG_DIR}/kustomization.yaml
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

A cluster gets two `Kustomization`s, which fill in variables such as `${cluster_name}` in the files below. The
cluster's `Kustomization` applies the `${WC_DIR}/cluster` directory and gets `Ready` once the cluster is up. The
apps' `Kustomization` applies the rest of `${WC_DIR}` only after that, so the apps install into a cluster that
exists.
The cluster itself is a Flux `HelmRelease` that installs the `release-aws` chart, built from the
[CAPA cluster base](/bases/clusters/capa) that ships with this repository. The chart version is
the Giant Swarm release, so the release the cluster runs is stored in Git. `release-aws` rejects a cluster name longer
than 20 characters. For other providers, see [Add a CAPx Workload Cluster base](./guides/clusters.md).

> **Shortcut:** [`kubectl gs gitops add workload-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-wc/)
> creates the same cluster, with the same file and resource names. After you pick a release in the first step below,
> run:
>
> ```sh
> kubectl gs gitops add workload-cluster --name ${WC_NAME} --organization ${ORG_NAME} \
>   --management-cluster ${MC_NAME} --repository-name ${GITOPS_REPO} \
>   --base bases/clusters/capa --release ${RELEASE_VERSION}
> ```
>
> The CLI still generates a `mapi` directory. Move what's in it up into `${WC_DIR}`, and take one `../` off the path
> to the base in the cluster's `kustomization.yaml`, which the CLI writes for `mapi/cluster`:
>
> ```sh
> mv ${WC_DIR}/mapi/apps ${WC_DIR}/mapi/cluster ${WC_DIR}/ && rmdir ${WC_DIR}/mapi
> yq -i '.resources |= map(sub("^\.\./"; ""))' ${WC_DIR}/cluster/kustomization.yaml
> ```
>
> The CLI doesn't add a region, so add it to the cluster's `kustomization.yaml`, with the `REGION` from the second step
> below:
>
> ```sh
> yq -i '.components = ["../../../../../../../bases/environments/regions/" + strenv(REGION)]' \
>   ${WC_DIR}/cluster/kustomization.yaml
> ```
>
> The CLI still writes a single `Kustomization` that applies all of `${WC_DIR}/mapi`, so the apps don't wait for the
> cluster. It writes it into `${ORG_DIR}/workload-clusters/${WC_NAME}.yaml`, in `default`, and lists it in
> `${ORG_DIR}/workload-clusters/kustomization.yaml`, which it needs: create that list as an empty one before you run
> the CLI if the organisation doesn't have it. Replace the CLI's `Kustomization` with the two of the last steps below,
> which go in the organisation's namespace, and add `${WC_DIR}/kustomization.yaml` as in the step before them. Then
> delete the CLI's file and list, which nothing applies:
>
> ```sh
> rm ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml ${ORG_DIR}/workload-clusters/kustomization.yaml
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
    mkdir -p ${WC_DIR}/cluster
    ```

    Then create its `kustomization.yaml`:

    ```sh
    cat <<EOF > ${WC_DIR}/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    components:
      - ../../../../../../../bases/environments/regions/${REGION}
    resources:
      - ../../../../../../../bases/clusters/capa
    EOF
    ```

    The cluster runs with the base's defaults. To add your own values, see
    [Creating a cluster from the CAPA cluster base](./add_wc_instance.md#creating-a-cluster-from-the-capa-cluster-base).
    Don't set `global.release.version` in them, because the chart sets it.

1. Create the list of apps to deploy to the cluster. It starts empty, and you add an app to it in the next step. First,
   create its directory:

    ```sh
    mkdir -p ${WC_DIR}/apps
    ```

    Then create the list:

    ```sh
    cat <<'EOF' > ${WC_DIR}/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    buildMetadata: [originAnnotations]
    namespace: org-${organization}
    resources: []
    EOF
    ```

    Then list it in `${WC_DIR}/kustomization.yaml`, which leaves out `cluster`, as the cluster has a
    `Kustomization` of its own:

    ```sh
    cat <<'EOF' > ${WC_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - apps/
    EOF
    ```

1. Create the cluster's `Kustomization`. With `prune: true`, Flux deletes what you delete from the cluster's files.
   It never deletes the cluster itself: the cluster's `HelmRelease`, from the CAPA cluster base, has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and the `giantswarm.io/prevent-deletion` label. Its health
   check waits until Cluster API reports the cluster `Available`, which takes up to its `timeout` of 30 minutes. It
   goes in the organisation's `namespace` directory, so the organisation's namespace `Kustomization` applies it into
   `org-${ORG_NAME}`, and it runs as that namespace's `automation` ServiceAccount. It names no namespace, and reads
   your `GitRepository` in `default`. Its `dependsOn` names the organisation's namespace `Kustomization`, so that one
   always applies a commit first:

    ```sh
    cat <<EOF > ${ORG_DIR}/namespace/workload-clusters/${WC_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${WC_NAME}
    spec:
      dependsOn:
        - name: ${MC_NAME}-organization-${ORG_NAME}
          namespace: default
      healthCheckExprs:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          current: status.conditions.exists(c, c.type == 'Available' && c.status == 'True')
      healthChecks:
        - apiVersion: cluster.x-k8s.io/v1beta2
          kind: Cluster
          name: ${WC_NAME}
          namespace: org-${ORG_NAME}
      interval: 10m
      path: ./${WC_DIR}/cluster
      postBuild:
        substitute:
          cluster_description: "${WC_NAME} managed by GitOps"
          cluster_name: "${WC_NAME}"
          organization: "${ORG_NAME}"
          release: "${RELEASE_VERSION}"
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
        namespace: default
      timeout: 30m
    EOF
    ```

1. Create the apps' `Kustomization`. It has the cluster's `Kustomization` in `dependsOn`, so Flux applies nothing of
   it until the cluster's is `Ready`:

    ```sh
    cat <<EOF > ${ORG_DIR}/namespace/workload-clusters/${WC_NAME}-apps.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${WC_NAME}-apps
    spec:
      dependsOn:
        - name: ${MC_NAME}-clusters-${WC_NAME}
      interval: 10m
      path: ./${WC_DIR}
      postBuild:
        substitute:
          cluster_description: "${WC_NAME} managed by GitOps"
          cluster_name: "${WC_NAME}"
          organization: "${ORG_NAME}"
          release: "${RELEASE_VERSION}"
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
        namespace: default
      timeout: 2m
    EOF
    ```

    Add both to the organization's list of clusters:

    ```sh
    yq -i '.resources += ["'"${WC_NAME}"'.yaml", "'"${WC_NAME}"'-apps.yaml"]' \
      ${ORG_DIR}/namespace/workload-clusters/kustomization.yaml
    ```

    Finally, commit and push:

    ```sh
    git add ${ORG_DIR} && git commit -m "Add workload cluster ${WC_NAME}" && git push
    ```

**Check:** the cluster takes 15 to 20 minutes to come up. Watch it with:

```sh
kubectl gs get clusters -n org-${ORG_NAME}
```

Once it's up, the cluster's `Kustomization` is `Ready`, and the apps' `Kustomization` after it:

```sh
flux get kustomizations -n org-${ORG_NAME} | grep ${MC_NAME}-clusters-${WC_NAME}
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
    export APP_DIR=${WC_DIR}/apps/hello-world
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
      labels:
        reconcile.fluxcd.io/watch: Enabled
    resources:
      - oci-repository.yaml
      - helm-release.yaml
    EOF
    ```

1. Add the app to the cluster's list of apps:

    ```sh
    yq -i '.resources += ["hello-world"]' ${WC_DIR}/apps/kustomization.yaml
    ```

1. Commit and push:

    ```sh
    git add ${WC_DIR}/apps && git commit -m "Deploy hello-world to ${WC_NAME}" && git push
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

Skip this step to keep the cluster. When you delete the cluster's files, Flux deletes its `Kustomization`s, its apps
and its configuration, but not the cluster: its `HelmRelease` has the `kustomize.toolkit.fluxcd.io/prune: disabled`
annotation, so Flux keeps it, and the `giantswarm.io/prevent-deletion` label, so nobody can delete it until the label
is removed. The cluster's `OCIRepository` has both too, and its `Cluster` the label. You remove the labels first, and
delete the `HelmRelease` and the `OCIRepository` by hand at the end. See [How it works](./how-it-works.md).

> **Warning:** `kubectl gs` doesn't write the annotation or the label yet. The `Organization` that `kubectl gs gitops
> add organization` writes doesn't have them, nor do the cluster `HelmRelease` and `OCIRepository` of a base that
> `kubectl gs gitops add base` writes. Add them by hand before you rely on them to keep those objects when their files
> are deleted. Without them on the `OCIRepository`, Flux deletes it and the `HelmRelease` it keeps loses its chart.

If an [application team](./guides/app-teams.md) delivers to the cluster with Flux on the management cluster, remove
the team from the cluster first, as that guide describes.

1. Remove the label from the cluster's `OCIRepository` and `HelmRelease`, and set
   `global.metadata.preventDeletion` to `false`, so that the chart removes it from the cluster's `Cluster` too:

    ```sh
    yq -i '.patches += [{"patch": "[{\"op\": \"remove\", \"path\": \"/metadata/labels/giantswarm.io~1prevent-deletion\"}]", "target": {"labelSelector": "giantswarm.io/prevent-deletion"}}, {"patch": "{\"apiVersion\": \"helm.toolkit.fluxcd.io/v2\", \"kind\": \"HelmRelease\", \"metadata\": {\"name\": \"cluster\"}, \"spec\": {\"values\": {\"global\": {\"metadata\": {\"preventDeletion\": false}}}}}", "target": {"kind": "HelmRelease"}}]' ${WC_DIR}/cluster/kustomization.yaml
    ```

    `spec.values` takes precedence over the ConfigMaps in `valuesFrom`, so this works whatever values the cluster has.
    Commit and push, and make Flux read the change right away:

    ```sh
    git commit -am "Remove the deletion protection of workload cluster ${WC_NAME}" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    ```

    Then wait until the `Cluster` has lost the label, which takes an upgrade of the chart. The `PREVENT-DELETION`
    column has to be empty:

    ```sh
    kubectl get clusters.cluster.x-k8s.io ${WC_NAME} -n org-${ORG_NAME} -L giantswarm.io/prevent-deletion
    ```

1. Remove the cluster from the organization's list. The cluster's `Kustomization`s are in
   `${ORG_DIR}/namespace/workload-clusters`, which the organisation's namespace `Kustomization` applies: the
   cluster's, the apps', and the `-direct` one if the cluster has out-of-band resources, which it applies to the
   workload cluster, see [Add a new Workload Cluster repository structure](./add_wc_structure.md#directory-tree). Take
   them out of that directory's list, save the names of the SOPS key Secrets they decrypt with, if any, and remove
   their files:

    ```sh
    unset KEYS KEY_FILE
    for f in ${WC_NAME}.yaml ${WC_NAME}-apps.yaml ${WC_NAME}-direct.yaml; do
      [ -f ${ORG_DIR}/namespace/workload-clusters/${f} ] || continue
      yq -i 'del(.resources[] | select(. == "'"${f}"'"))' ${ORG_DIR}/namespace/workload-clusters/kustomization.yaml
      KEYS="${KEYS} $(yq '.spec.decryption.secretRef.name // ""' ${ORG_DIR}/namespace/workload-clusters/${f})"
      git rm -q ${ORG_DIR}/namespace/workload-clusters/${f}
    done
    export KEYS=$(echo ${KEYS} | tr ' ' '\n' | sort -u | tr '\n' ' ')
    ```

    If `KEYS` isn't empty, the cluster's `Kustomization`s decrypt with key Secrets in the organisation's namespace,
    which another cluster's `Kustomization`s may share. Check whether one does:

    ```sh
    yq ea 'select(.spec.decryption.secretRef.name as $n | strenv(KEYS) | split(" ") | any_c(. == $n)) |
      filename + ": " + .spec.decryption.secretRef.name' ${ORG_DIR}/namespace/workload-clusters/*.yaml
    ```

    If this prints a file, that cluster uses the key it names: keep the key, and take its name out of `KEYS`. Find the
    file of each key that's left, such as `${WC_NAME}.gpgkey.enc.yaml`, in the organisation's `namespace/secrets`,
    where everything in the organisation's namespace goes, and remove it and its entry in
    `namespace/secrets/kustomization.yaml`. That file protects the keys as the management cluster's
    `secrets/kustomization.yaml` does, see [Add an organization](./add_org.md):

    ```yaml
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
    resources:
      - ${WC_NAME}.gpgkey.enc.yaml
    ```

    Remove them:

    ```sh
    for key in $(echo ${KEYS}); do
      export KEY_FILE=$(basename "$(KEY=${key} yq ea 'select(.metadata.name == strenv(KEY)) | filename' ${ORG_DIR}/namespace/secrets/*.enc.yaml)")
      yq -i 'del(.resources[] | select(. == strenv(KEY_FILE)))' ${ORG_DIR}/namespace/secrets/kustomization.yaml
      git rm ${ORG_DIR}/namespace/secrets/${KEY_FILE}
    done
    ```

    Remove the cluster's directory, then commit and push everything in one go:

    ```sh
    git rm -r ${WC_DIR} && git commit -am "Delete workload cluster ${WC_NAME}" && git push
    ```

1. Make Flux read the change right away:

    ```sh
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-organization-${ORG_NAME} -n default
    ```

    Flux deletes the cluster's `Kustomization`s, which delete the cluster's apps and configuration first, and the
    `-direct` one deletes the out-of-band resources from the workload cluster. Wait until they're gone. They're in the
    organisation's namespace:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME} \
      kustomization/${MC_NAME}-clusters-${WC_NAME}-apps -n org-${ORG_NAME} --timeout=10m
    ```

    If the cluster has a `-direct` `Kustomization`, wait for it too:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME}-direct -n org-${ORG_NAME} --timeout=10m
    ```

    The `-direct` `Kustomization` reaches the workload cluster through the cluster's kubeconfig Secret, which goes with
    the cluster. So it has to be gone before you delete the cluster in the last step. Once the cluster is gone, so is
    its kubeconfig Secret, Flux can't reach the cluster any more, and the `-direct` `Kustomization` stays `Terminating`
    for good.

    If `KEYS` isn't empty, delete the key Secrets now. Flux keeps them on the management cluster, as it does every
    SOPS key Secret, see [How it works](./how-it-works.md). Remove their label first:

    ```sh
    for key in $(echo ${KEYS}); do
      kubectl label secret ${key} -n org-${ORG_NAME} giantswarm.io/prevent-deletion-
      kubectl delete secret ${key} -n org-${ORG_NAME}
    done
    ```

1. Flux doesn't wait for the cluster's apps to be uninstalled. Their `HelmRelease`s go once helm-controller has
   uninstalled them from the workload cluster, and it needs the cluster to do that, so wait for them:

    ```sh
    until [ -z "$(kubectl get helmrelease -n org-${ORG_NAME} \
        -l 'kustomize.toolkit.fluxcd.io/name in ('"${MC_NAME}-clusters-${WC_NAME},${MC_NAME}-clusters-${WC_NAME}-apps"'),kustomize.toolkit.fluxcd.io/namespace=org-'"${ORG_NAME}" \
        --field-selector metadata.name!=${WC_NAME} -o name)" ]; do sleep 10; done
    ```

1. Finally, delete the cluster's `HelmRelease`, which no longer has the label. This deletes the cluster. Then delete
   its `OCIRepository`:

    ```sh
    kubectl delete helmrelease ${WC_NAME} -n org-${ORG_NAME}
    kubectl delete ocirepository ${WC_NAME} -n org-${ORG_NAME}
    ```

## Next steps

- Keep secrets in a secret manager instead, with External Secrets Operator: [Getting started](./getting-started.md).
- Keep secrets in the repository, encrypted with SOPS: create a
  [GPG key](./add_wc_structure.md#create-flux-gpg-regular-key-pair-optional-step) or
  [age key](./add_wc_structure.md#create-an-age-key-pair-optional-step) for the cluster, then
  [provide encrypted values](./guides/add-app.md#providing-encrypted-values).
- Reuse an app's configuration across clusters: [App Templates](./guides/app-templates.md). Deploy several apps
  together: [Stacks](./guides/stacks.md).
- Pin the release and app versions of dev, staging and production clusters per stage:
  [Add Workload Cluster environments](./guides/environments.md).
- Understand how the repository is organized: [Repository structure](./reference/repo-structure.md).
- See which key decrypts which files: [SOPS keys](./reference/sops-keys.md).

[github-token]: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token
