# Getting started

This guide takes you from a fork of this repository to a running workload cluster with an app, all managed by Flux.
You connect your management cluster to the repository, add an organization, create a workload cluster, then deploy
and update an app.

Every change goes the same way: you commit a file, push it, and Flux on the management cluster applies it. To learn
more about the approach, see
[GitOps at Giant Swarm](https://docs.giantswarm.io/tutorials/continuous-deployment/gitops-at-giantswarm/).

No secret is stored in the repository. Secrets live in your secret manager, such as Vault or AWS Secrets Manager, and
[External Secrets Operator](https://docs.giantswarm.io/overview/security/external-secrets-operator/) (ESO) copies
them into the management cluster. If you'd rather keep secrets in the repository, encrypted, follow
[Getting started with SOPS](./getting-started-sops.md) instead.

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
  [`kubectl gs`](https://docs.giantswarm.io/reference/kubectl-gs/), `flux` and `yq`,
- access to the management cluster, see
  [Access to the platform API](https://docs.giantswarm.io/getting-started/access-to-platform-api/). Log in with
  `kubectl gs login API_URL`, where `API_URL` is the management cluster's Kubernetes API URL. After that, the context
  is named `gs-MC_NAME`. You need write access to the `default` and `org-*` namespaces,
- a `ClusterSecretStore` on the management cluster that can read your secret manager. ESO runs on every Giant Swarm
  management cluster. To create a store, see
  [Using External Secrets Operator](https://docs.giantswarm.io/tutorials/security/external-secrets-operator/). To
  only try this guide, create a [secret store for testing](./appendices.md#secret-store-for-testing),
- a fork of this repository, cloned locally. Run all commands from the root of the clone.

The fork comes with example directories named `MC_NAME`, `ORG_NAME`, `WC_NAME` and so on. Flux ignores them, so you
can keep them for reference.

Export the names used in all the commands below:

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export ORG_NAME=ORGANIZATION         # organization name, without the `org-` prefix
export WC_NAME=CLUSTER_NAME          # name of the new workload cluster, lowercase letters and digits
export GITOPS_REPO=REPO_NAME         # name for the Flux GitRepository, for example `gitops`
export GITOPS_REPO_URL=https://github.com/YOUR_ORG/YOUR_REPO
export SECRET_STORE=STORE_NAME       # name of the ClusterSecretStore

export MC_DIR=management-clusters/${MC_NAME}
export ORG_DIR=${MC_DIR}/organizations/${ORG_NAME}
export WC_DIR=${ORG_DIR}/workload-clusters/${WC_NAME}
```

Note that the variables only live in your current shell. If you open a new one, run the exports again.

If you use namespaced `SecretStore`s instead, you need one in `default` and one in `org-${ORG_NAME}`. Then set
`kind: SecretStore` in the `ExternalSecret`s below.

## 1. Connect the management cluster

Flux on the management cluster needs two things: access to the repository, and a `Kustomization` that tells it which
directory to apply. ESO gives it the repository credentials from your secret manager.

> **Shortcut:** [`kubectl gs gitops add management-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-mc/)
> does steps 1 and 2 for you:
>
> ```sh
> kubectl gs gitops add management-cluster --name ${MC_NAME} --repository-name ${GITOPS_REPO} --skip-encryption
> ```
>
> `--skip-encryption` leaves out the SOPS directories this guide doesn't use. It needs kubectl-gs 5.11.0 or newer.
> Then continue with step 3.

1. Create the management cluster's directory:

    ```sh
    mkdir -p ${MC_DIR}/organizations
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
      interval: 1m
      path: ./management-clusters/${MC_NAME}
      prune: false
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
      timeout: 2m
    EOF
    ```

1. Commit and push:

    ```sh
    git add ${MC_DIR} && git commit -m "Add management cluster ${MC_NAME}" && git push
    ```

1. (Optional) Give Flux access to the repository. Skip this if the `github-https-credentials` Secret already exists in
   the `default` namespace and can read this repository.

    First, create a GitHub token with read access to the repository's contents, for example a
    [fine-grained personal access token][github-token]. Store it in your secret manager, then save the name of that
    secret:

    ```sh
    export GITHUB_TOKEN_KEY=gitops/github-token
    ```

    Create an `ExternalSecret`. ESO reads the token and writes it into the `github-https-credentials` Secret, in the
    format Flux expects:

    ```sh
    cat <<EOF | kubectl apply -f -
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: github-https-credentials
      namespace: default
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: ClusterSecretStore
        name: ${SECRET_STORE}
      target:
        name: github-https-credentials
        template:
          data:
            username: git
            password: "{{ .token }}"
      data:
        - secretKey: token
          remoteRef:
            key: ${GITHUB_TOKEN_KEY}
    EOF
    ```

    If the secret in your secret manager holds several fields, add `property: FIELD_NAME` under `remoteRef`.

    **Check:** the `ExternalSecret` reports `SecretSynced`:

    ```sh
    kubectl get externalsecret github-https-credentials -n default
    ```

1. Create the `GitRepository`. Its `ignore` field keeps Flux from reading the example directories:

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
> creates the same files:
>
> ```sh
> kubectl gs gitops add organization --name ${ORG_NAME} --management-cluster ${MC_NAME}
> ```

First, create the organization's directory:

```sh
mkdir -p ${ORG_DIR}/workload-clusters
```

Create the `Organization`:

```sh
cat <<EOF > ${ORG_DIR}/${ORG_NAME}.yaml
apiVersion: security.giantswarm.io/v1alpha1
kind: Organization
metadata:
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
`${cluster_name}` in the files below. The cluster itself is an App that installs the `cluster-aws` chart, built from
the [CAPA base](/bases/clusters/capa/template) that ships with this repository. For other providers, see
[Add a CAPx Workload Cluster template](./add_wc_template.md).

> **Shortcut:** [`kubectl gs gitops add workload-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-wc/)
> creates the same cluster, with slightly different file names. It looks up the `cluster-aws` version of the release in
> [giantswarm/releases](https://github.com/giantswarm/releases), and needs kubectl-gs 5.11.0 or newer. After you pick
> a release in the first step below, run:
>
> ```sh
> kubectl gs gitops add workload-cluster --name ${WC_NAME} --organization ${ORG_NAME} \
>   --management-cluster ${MC_NAME} --repository-name ${GITOPS_REPO} \
>   --base bases/clusters/capa/template --release ${RELEASE_VERSION}
> ```
>
> Then commit and push, as in the last step below.

1. List the Giant Swarm releases and pick one:

    ```sh
    kubectl get releases.release.giantswarm.io
    ```

    Export the release you picked:

    ```sh
    export RELEASE_VERSION=36.1.0
    ```

    Then read the version of the `cluster-aws` chart it ships:

    ```sh
    export CLUSTER_APP_VERSION=$(kubectl get releases.release.giantswarm.io aws-${RELEASE_VERSION} -o yaml |
    yq '.spec.components[] | select(.name == "cluster-aws") | .version')
    ```

1. Create the cluster definition. It points at the base, sets the chart version, and adds your values on top of the
   base's defaults. First, create its directory:

    ```sh
    mkdir -p ${WC_DIR}/mapi/cluster ${WC_DIR}/mapi/apps
    cat <<'EOF' > ${WC_DIR}/mapi/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: org-${organization}
    resources: []
    EOF
    ```

    Put your values into a ConfigMap. They follow the
    [`cluster-aws` schema](https://github.com/giantswarm/cluster-aws/blob/main/helm/cluster-aws/README.md):

    ```sh
    cat <<EOF > ${WC_DIR}/mapi/cluster/cluster_userconfig.yaml
    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: \${cluster_name}-userconfig
      namespace: org-\${organization}
    data:
      values: |
        global:
          release:
            version: ${RELEASE_VERSION}
    EOF
    ```

    Create a patch that sets the chart version on the cluster App and points it at your values:

    ```sh
    cat <<EOF > ${WC_DIR}/mapi/cluster/patch_userconfig.yaml
    apiVersion: application.giantswarm.io/v1alpha1
    kind: App
    metadata:
      name: \${cluster_name}
      namespace: org-\${organization}
    spec:
      version: "${CLUSTER_APP_VERSION}"
      userConfig:
        configMap:
          name: \${cluster_name}-userconfig
          namespace: org-\${organization}
    EOF
    ```

    Then tie the base, the values and the patch together:

    ```sh
    cat <<EOF > ${WC_DIR}/mapi/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    patches:
      - path: patch_userconfig.yaml
    resources:
      - ../../../../../../../../bases/clusters/capa/template
      - cluster_userconfig.yaml
    EOF
    ```

1. Create the cluster's `Kustomization`. Note that `prune: false` keeps Flux from deleting the cluster if the file is
   removed by mistake:

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
      prune: false
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
> resources to the management cluster directly, outside of Git. Note that `:values` in `--values-from` needs
> kubectl-gs 5.11.0 or newer. After the first step below, run:
>
> ```sh
> kubectl gs deploy chart --chart-name hello-world --version 3.2.3 \
>   --organization ${ORG_NAME} --target-cluster ${WC_NAME} --target-namespace hello-world \
>   --values-from ConfigMap/${WC_NAME}-cluster-values:values \
>   --values-from ConfigMap/${WC_NAME}-hello-world-values:values \
>   --values-from Secret/${WC_NAME}-hello-world-user-secrets:values:optional \
>   --dry-run | APP_DIR=${APP_DIR:?run the first step below} yq -s 'strenv(APP_DIR) + "/" + (.kind | downcase) + ".yaml"'
> ```
>
> This writes `ocirepository.yaml` and `helmrelease.yaml`. Then continue with the `values.yaml` step.

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
    cat <<'EOF' > ${APP_DIR}/ocirepository.yaml
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
    cat <<'EOF' > ${APP_DIR}/helmrelease.yaml
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
        - kind: Secret
          name: ${cluster_name}-hello-world-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

    The `${cluster_name}-cluster-values` ConfigMap is created for every workload cluster and gives the chart values
    such as `baseDomain`. Values listed later in `valuesFrom` win. The last entry is optional. You can fill it with
    secret values a few steps below.

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
      - helmrelease.yaml
      - ocirepository.yaml
    EOF
    ```

1. (Optional) Give the app secret values. Store them in your secret manager as Helm values in YAML. The hello-world
   chart has no secret settings, so as an example, store this:

    ```yaml
    podAnnotations:
      example.com/source: secret-manager
    ```

    Save the name of that secret:

    ```sh
    export APP_SECRET_KEY=gitops/hello-world-values
    ```

    Create an `ExternalSecret`. ESO turns the values into the `${cluster_name}-hello-world-user-secrets` Secret the
    `HelmRelease` reads:

    ```sh
    cat <<EOF > ${APP_DIR}/externalsecret.yaml
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: \${cluster_name}-hello-world-user-secrets
      namespace: org-\${organization}
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: ClusterSecretStore
        name: ${SECRET_STORE}
      target:
        name: \${cluster_name}-hello-world-user-secrets
      data:
        - secretKey: values
          remoteRef:
            key: ${APP_SECRET_KEY}
    EOF
    ```

    Add it to the app's `kustomization.yaml`:

    ```sh
    yq -i '.resources += ["externalsecret.yaml"]' ${APP_DIR}/kustomization.yaml
    ```

1. Commit and push:

    ```sh
    git add ${APP_DIR} && git commit -m "Deploy hello-world to ${WC_NAME}" && git push
    ```

**Check:** the release is `Ready` on the management cluster:

```sh
flux get helmreleases ${WC_NAME}-hello-world -n org-${ORG_NAME}
```

The pods run in the workload cluster:

```sh
kubectl --context ${WC_CONTEXT} get pods -n hello-world
```

If you added secret values, the `ExternalSecret` reports `SecretSynced`:

```sh
kubectl get externalsecret ${WC_NAME}-hello-world-user-secrets -n org-${ORG_NAME}
```

Learn more:
[Deploying an app with a Flux HelmRelease](https://docs.giantswarm.io/tutorials/fleet-management/app-platform/deploy-app-helmrelease/).

## 5. Update the app

To update an app, change its files and push. First, upgrade the chart:

```sh
yq -i '.spec.ref.tag = "3.2.4"' ${APP_DIR}/ocirepository.yaml
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

To change a secret value, change it in your secret manager. ESO copies it within the `refreshInterval`, and Flux
upgrades the release at its next `interval`.

To let Flux install new chart versions by itself, replace `tag` with a `semver` range in the `OCIRepository`. For
example, `semver: 3.2.x` installs every new patch version.

## 6. Delete the cluster (optional)

Skip this step to keep the cluster. Deleting it takes two pushes, so that a mistake can't remove a cluster:

1. Allow the cluster's `Kustomization` to delete what it created:

    ```sh
    yq -i '.spec.prune = true' ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml
    ```

    Commit and push:

    ```sh
    git commit -am "Allow deletion of ${WC_NAME}" && git push
    ```

1. Wait until the cluster's `Kustomization` shows the new revision:

    ```sh
    flux get kustomizations ${MC_NAME}-clusters-${WC_NAME} -n default
    ```

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

    Finally, delete the cluster's `Kustomization`. Flux then deletes the cluster and its apps:

    ```sh
    kubectl delete kustomization ${MC_NAME}-clusters-${WC_NAME} -n default
    ```

    Note that you delete it by hand because the management cluster's `Kustomization` has `prune: false`. It doesn't
    delete the cluster's `Kustomization` by itself.

## Next steps

- Keep secrets in the repository instead, encrypted with SOPS: [Getting started with SOPS](./getting-started-sops.md).
- Learn more about ESO, and the risks of depending on it:
  [External Secrets Operator](https://docs.giantswarm.io/overview/security/external-secrets-operator/).
- Reuse an app's configuration across clusters: [App Templates](./apps/add_app_template.md) and
  [App Sets](./apps/app_sets.md).
- Run dev, staging and production clusters from shared templates:
  [Add Workload Cluster environments](./add_wc_environments.md).
- Understand how the repository is organized: [Repository structure](./repo_structure.md).

[github-token]: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token
