# Getting started

By the end of this tutorial you'll have one organisation, one workload cluster in it and one app running on that
cluster, all described in files in your fork of this repository and applied by Flux. You build it up a step at a time:
connect the management cluster, add the organisation, create the cluster, deploy the app and update it. If you'd like
your cloud bill back afterwards, the last step deletes the cluster again.

Every change goes the same way: you write a file, commit it and push, and Flux on the management cluster applies it.
Think of the repository as a planting plan and Flux as the gardener. Every few minutes it walks round, plants whatever
is in the plan but not yet in the ground, and, because the `Kustomization`s here set `prune: true`, pulls up whatever
you've taken out of the plan. That last part is why a few objects in this tutorial carry a label that tells Flux to
leave them alone: some things you don't want gone just because a file went missing. For more on the approach, see
[GitOps at Giant Swarm](https://docs.giantswarm.io/tutorials/continuous-deployment/gitops-at-giantswarm/).

A cluster and its apps need secrets, and this repository supports two ways to keep them:

- [SOPS](https://github.com/getsops/sops) encrypts them and keeps them in the repository. Only Flux on the management
  cluster holds the key that decrypts them.
- [External Secrets Operator](https://docs.giantswarm.io/overview/security/external-secrets-operator/) (ESO) reads them
  from your secret manager, such as AWS Secrets Manager or Azure Key Vault, and writes them into the management
  cluster. ESO runs on every Giant Swarm management cluster.

You can use SOPS on its own, ESO on its own, or both. This tutorial uses both, each for what it does best. SOPS keeps
the two secrets Flux needs before it can read anything at all: the key that decrypts the repository, and the token
that reads it. ESO gives the app its secret values. If you only want one of them:

- **SOPS only:** follow the tutorial, but leave out the secret store in step 2 and the `ExternalSecret` in step 4.
  Encrypt the app's secret values with a key of the cluster's own instead: see
  [Add a workload cluster key (age)](../../how-to/sops.md#add-a-workload-cluster-key-age) and
  [Encrypt an app's values](../../how-to/sops.md#encrypt-an-apps-values).
- **ESO only:** leave out the master key, the `.sops.yaml` rules, the `secrets` directory and the `decryption` fields
  in step 1 and step 2, and take Flux's token from your secret manager:
  [Keep the repository token in your secret manager](../../how-to/external-secrets.md#keep-the-repository-token-in-your-secret-manager).

Which secret belongs where, and what each way costs you, is in [Secrets](../../explanation/secrets.md).

By the end, your fork has these new files:

```text
.sops.yaml                                 two new rules for the master key
management-clusters/${MC_NAME}/
├── ${MC_NAME}.yaml                        applies this directory                         (step 1)
├── .sops.keys/.sops.master.asc            the master key's public half
├── secrets/                               the master key and the repository token, encrypted
└── organizations/${ORG_NAME}/
    ├── ${ORG_NAME}.yaml                   the Organization                               (step 2)
    ├── kustomization.yaml
    ├── namespace.yaml                     applies namespace/ into org-${ORG_NAME}
    ├── namespace/kustomization.yaml
    ├── multicluster/secret-stores/        the organisation's SecretStore
    └── workload-clusters/
        ├── kustomization.yaml
        ├── ${WC_NAME}.yaml                applies the cluster                            (step 3)
        ├── ${WC_NAME}-apps.yaml           applies its apps once the cluster is up
        └── ${WC_NAME}/
            ├── cluster/                   the cluster, from the CAPA cluster base
            └── apps/hello-world/          the app                                        (step 4)
```

- [Before you start](#before-you-start)
- [1. Connect the management cluster](#1-connect-the-management-cluster)
- [2. Add an organisation](#2-add-an-organisation)
- [3. Create a workload cluster](#3-create-a-workload-cluster)
- [4. Deploy an app](#4-deploy-an-app)
- [5. Update the app](#5-update-the-app)
- [6. Delete the cluster (optional)](#6-delete-the-cluster-optional)
- [Next steps](#next-steps)

## Before you start

You need:

- the [tools](../../reference/tools.md#tools) this tutorial runs: `git`, `kubectl`,
  [`kubectl gs`](https://docs.giantswarm.io/reference/kubectl-gs/), `flux`, `gpg`, `sops` and `yq`. The
  [kubectl-gs version](../../reference/tools.md#kubectl-gs-version) table says which release each `kubectl gs gitops`
  command needs,
- access to the management cluster, see
  [Access to the platform API](https://docs.giantswarm.io/getting-started/access-to-platform-api/). Log in with
  `kubectl gs login API_URL`, where `API_URL` is the management cluster's Kubernetes API URL. After that, the context
  is named `gs-MC_NAME`. You need write access to the `default` and `org-*` namespaces,
- a fork of this repository, cloned locally. Run every command from the root of the clone.

The fork comes with example directories named `MC_NAME`, `ORG_NAME`, `WC_NAME` and so on. Flux ignores them, so leave
them where they are: they're the worked answers at the back of the book, and you'll find yourself checking them.

`kubectl gs gitops` can write most of the files in this tutorial for you, and each step names the command that does.
You write them by hand here, so that you know what each one is for when you come to change it.

Export the names the commands use:

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export ORG_NAME=ORGANISATION         # organisation name, without the `org-` prefix
export WC_NAME=CLUSTER_NAME          # name of the new workload cluster, lowercase letters and digits, at most 20 characters
export GITOPS_REPO=REPO_NAME         # name for the Flux GitRepository, for example `gitops`
export GITOPS_REPO_URL=https://github.com/YOUR_ORG/YOUR_REPO

export MC_DIR=management-clusters/${MC_NAME}
export ORG_DIR=${MC_DIR}/organizations/${ORG_NAME}
export WC_DIR=${ORG_DIR}/workload-clusters/${WC_NAME}
```

The variables live only in your current shell. If you open a new one, run the exports again.

## 1. Connect the management cluster

Flux on the management cluster needs three things before it can do anything for you: a key to decrypt what's
encrypted in the repository, a token to read the repository, and a `Kustomization` that tells it which directory to
apply. Both secrets live in the repository, encrypted with SOPS. There's a catch, though: Flux can't read the
repository until it has the token, and it can't decrypt the token until it has the key. So you hand both over
yourself, once, and from then on Flux keeps them up to date from Git like everything else.

> **Shortcut:** [`kubectl gs gitops add management-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-mc/)
> writes the management cluster's directory and its `Kustomization`. With `--gen-master-key`, it also writes a new
> master key in `secrets`, its public key in `.sops.keys` and the first `.sops.yaml` rule. It doesn't write the
> repository token or the second rule, and its `Kustomization` doesn't prune. See
> [Management cluster](../../how-to/kubectl-gs.md#management-cluster) for the command and what to change afterwards.

1. Create the management cluster's directory. `.sops.keys` holds public keys, `secrets` the encrypted secrets Flux
   needs, and `organizations` the organisations you add in the next step:

    ```sh
    mkdir -p ${MC_DIR}/.sops.keys ${MC_DIR}/secrets ${MC_DIR}/organizations
    ```

1. Create the `Kustomization` that applies the management cluster's directory. Its `decryption` field names the
   Secret that will hold the master key, so Flux can decrypt what it applies:

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

1. Create the master key, a GPG key without a passphrase, as Flux has nobody to type one in. If you already have a
   master key for this management cluster, skip this and import yours from your password manager instead, with
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

    Save its fingerprint for the next commands:

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

    > [!Caution]
    > Until you encrypt it a few steps below, this file holds the private key in plain text. Don't add it to Git
    > before then.

1. Share the public key in the repository, so that anyone can encrypt for Flux, but only Flux can decrypt:

    ```sh
    gpg --export --armor "${KEY_FP}" > ${MC_DIR}/.sops.keys/.sops.master.asc
    ```

    Then add two rules to `.sops.yaml`, which tells `sops` which key encrypts which file. The first covers the
    `secrets` directory. The second covers the SOPS keys you may give your workload clusters later, which go in their
    organisation's `namespace/secrets`, see [Encryption rules](../../reference/sops-keys.md#encryption-rules):

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

1. Write Flux's token for the repository into the `github-https-credentials` Secret. Create a GitHub token with read
   access to the repository's contents, for example a [fine-grained personal access token][github-token]. First,
   check that nobody got there before you:

    ```sh
    kubectl get secret github-https-credentials -n default
    ```

    > [!Caution]
    > If the Secret already exists, another `GitRepository` may read it, and replacing it would cut that one off.
    > If it can read your repository too, skip the rest of this step, and leave
    > `github-https-credentials.enc.yaml` out of the `secrets` list below.

    Read the token without it landing in your shell history, and write the Secret:

    ```sh
    read -rs GITHUB_TOKEN
    kubectl create secret generic github-https-credentials --namespace=default \
    --from-literal=username=git --from-literal=password="${GITHUB_TOKEN}" --dry-run=client -o yaml \
    > ${MC_DIR}/secrets/github-https-credentials.enc.yaml
    unset GITHUB_TOKEN
    ```

    The same caution applies: the token is in plain text until the next step but one.

1. Apply both Secrets, so that Flux has them before it needs them. If the management cluster already has this master
   key, applying it again changes nothing:

    ```sh
    kubectl apply -f ${MC_DIR}/secrets/
    ```

1. Encrypt both files in place. From now on the repository keeps only the encrypted copies:

    ```sh
    for f in ${MC_DIR}/secrets/*.enc.yaml; do sops --encrypt --in-place "${f}"; done
    ```

    List them in the `secrets` directory's `kustomization.yaml`. Without these two Secrets, Flux can neither read nor
    decrypt the repository, so the annotation keeps Flux from deleting them when their files go, and the label keeps
    anyone else from deleting them by accident:

    ```sh
    cat <<EOF > ${MC_DIR}/secrets/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    # Flux reads and decrypts the repository with these: deleting one stops GitOps for the management cluster
    commonAnnotations:
      kustomize.toolkit.fluxcd.io/prune: disabled
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
          # nobody can delete them, Flux included, until this label is removed
          giantswarm.io/prevent-deletion: "true"
    resources:
      - ${MC_NAME}.gpgkey.enc.yaml
      - github-https-credentials.enc.yaml
    EOF
    ```

1. (Optional) Print the private key and store it in your password manager, if it isn't there already. You need it
   whenever you decrypt a file yourself, or add a key, see
   [Keep a private key in a password manager](../../how-to/sops.md#keep-a-private-key-in-a-password-manager):

    ```sh
    gpg --export-secret-keys --armor "${KEY_FP}"
    ```

    Then remove it from your machine. You can still encrypt with the public key:

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

1. Commit and push:

    ```sh
    git add .sops.yaml ${MC_DIR} && git commit -m "Add management cluster ${MC_NAME}" && git push
    ```

1. Create the `GitRepository`, which tells Flux where the repository is and how to read it. Its `ignore` field keeps
   Flux away from the example directories:

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

    That's the last thing you apply by hand. From here on, Flux applies what you push, the `Kustomization` itself
    included.

**Check:** the `GitRepository` is `Ready`:

```sh
flux get sources git ${GITOPS_REPO} -n default
```

So is the `Kustomization`:

```sh
flux get kustomizations ${MC_NAME}-gitops -n default
```

## 2. Add an organisation

An organisation groups clusters, and owns the `org-${ORG_NAME}` namespace they live in. If the organisation already
exists, these steps bring it under GitOps. You'll also give it a secret store here, as every cluster in the
organisation reads its secrets through the organisation's namespace.

> **Shortcut:** [`kubectl gs gitops add organization`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-org/)
> writes the `Organization`, without its annotation and label, and the organisation's empty list of clusters. It
> doesn't write the organisation's `kustomization.yaml`, the namespace `Kustomization` or the secret store. See
> [Organisation](../../how-to/kubectl-gs.md#organisation) for the command and what to add afterwards.

1. Create the organisation's directory. `namespace` holds what the organisation keeps in its namespace,
   `workload-clusters` its clusters, and `multicluster` what all of its clusters share:

    ```sh
    mkdir -p ${ORG_DIR}/namespace ${ORG_DIR}/workload-clusters ${ORG_DIR}/multicluster/secret-stores
    ```

1. Create the `Organization`. organization-operator creates the `org-${ORG_NAME}` namespace for it. Deleting the
   `Organization` deletes that namespace, with every cluster in it, so the annotation keeps Flux from deleting it
   when its file goes, and the label keeps anyone else from deleting it:

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

1. Create the organisation's namespace `Kustomization`. Your management cluster's `Kustomization` applies only the
   `Organization` and objects in `default`, so it works before the namespace exists. This one, in `default`, applies
   the organisation's `namespace` directory into `org-${ORG_NAME}`. It fails until organization-operator has created
   the namespace, and succeeds on its next retry. Its `dependsOn` names your management cluster's `Kustomization`, so
   that one always applies a commit first. Its `decryption` field is there for the SOPS keys you may give your
   clusters later, which go in `namespace/secrets`. `ORG_NAME` and `org-ORG_NAME` are placeholders that the
   organisation's `kustomization.yaml` fills in, see
   [Flux Kustomizations](../../reference/repo-structure.md#flux-kustomizations):

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
    ```

    The `namespace` directory lists what goes into the namespace. Two of its entries live outside it, next to what
    they belong with: the organisation's list of clusters, empty for now, and its secret stores:

    ```sh
    cat <<EOF > ${ORG_DIR}/namespace/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - ../multicluster/secret-stores
      - ../workload-clusters
    EOF
    cat <<EOF > ${ORG_DIR}/workload-clusters/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    ```

1. Create the organisation's secret store. The app in step 4 reads its secret values through it. Here you use a
   stand-in: the [fake provider](https://external-secrets.io/latest/provider/fake/) of ESO keeps the values in the
   store itself, so you need no secret manager and no credentials to try the whole tutorial. Anyone who can read the
   repository can read what's in it, so never put a real secret in it.

    ```sh
    export SECRET_STORE=gitops-test
    cat <<EOF > ${ORG_DIR}/multicluster/secret-stores/secret-store.yaml
    apiVersion: external-secrets.io/v1
    kind: SecretStore
    metadata:
      name: ${SECRET_STORE}
    spec:
      provider:
        fake:
          data:
            - key: gitops/hello-world-values
              value: |
                podAnnotations:
                  example.com/source: secret-manager
    EOF
    cat <<EOF > ${ORG_DIR}/multicluster/secret-stores/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - secret-store.yaml
    EOF
    ```

    For the real thing, replace `secret-store.yaml` with a store for your secret manager, and set `SECRET_STORE` to
    its name. The bases in [bases/secret_stores](../../../bases/secret_stores) read AWS Secrets Manager or Azure Key
    Vault with workload identity, so no credential is stored anywhere, see
    [Create a SecretStore for your secret manager](../../how-to/external-secrets.md#create-a-secretstore-for-your-secret-manager).
    If your secret manager can't use workload identity, its store needs a credential, such as an access key: keep it
    in a Secret encrypted with SOPS in `namespace/secrets`, with an
    [organisation key](../../how-to/sops.md#add-an-organisation-key).

1. Create the organisation's `kustomization.yaml`. The management cluster's `Kustomization` applies what it lists,
   the `Organization` and the namespace `Kustomization`. Its replacements copy the `Organization`'s name into the
   namespace `Kustomization`'s `organization` variable and its `targetNamespace`, so you set the name in one place
   only, see [The organisation's name](../../reference/repo-structure.md#the-organisations-name). The quoted `'EOF'`
   keeps the placeholders as they are:

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

1. Commit and push:

    ```sh
    git add ${ORG_DIR} && git commit -m "Add organisation ${ORG_NAME}" && git push
    ```

**Check:** the namespace `org-${ORG_NAME}` exists, which takes about a minute:

```sh
kubectl get namespace org-${ORG_NAME}
```

The namespace `Kustomization` is `Ready` once it has applied into it:

```sh
flux get kustomizations ${MC_NAME}-organization-${ORG_NAME} -n default
```

The store is `Ready`:

```sh
kubectl get secretstore ${SECRET_STORE} -n org-${ORG_NAME}
```

## 3. Create a workload cluster

The cluster itself is a Flux `HelmRelease` that installs the `release-aws` chart, built from the
[CAPA cluster base](../../../bases/clusters/capa) that ships with this repository. The chart's version is the Giant
Swarm release, so the release your cluster runs is written down in Git, where you can see it and change it.

A cluster gets two `Kustomization`s, which fill in variables such as `${cluster_name}` in its files. The cluster's
`Kustomization` applies `${WC_DIR}/cluster`, and is `Ready` once the cluster is up. The apps' `Kustomization` applies
the rest of `${WC_DIR}`, but only after that, so the apps never try to install into a cluster that isn't there yet.

> **Shortcut:** [`kubectl gs gitops add workload-cluster`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-wc/)
> writes the cluster's directory from a base, and its `Kustomization`, which it lists in the organisation's
> `workload-clusters`. It still writes a `mapi` directory, no region, and one `Kustomization` for the whole cluster,
> in `default`, instead of the two below. See [Workload cluster](../../how-to/kubectl-gs.md#workload-cluster) for
> the command and how to bring its files in line with the ones below.

1. List the Giant Swarm releases and pick an AWS one from v34.0.0 on. These have a `release-aws` chart:

    ```sh
    kubectl get releases.release.giantswarm.io
    ```

    Export the release you picked, without the `aws-` prefix. The version below is only an example:

    ```sh
    export RELEASE_VERSION=36.2.0
    ```

1. Pick the cluster's region from [bases/environments/regions](../../../bases/environments/regions). Every cluster
   needs one. Without it, the chart creates the cluster wherever the management cluster's nodes happen to be, and
   `tools/test-all-ff` fails. To add a region, see
   [Regions](../intermediate/stages-and-regions.md#regions).

    ```sh
    export REGION=eu_central
    ```

1. Create the cluster definition. It points at the CAPA cluster base and adds the region as a component. First,
   create its directory:

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

    The cluster runs with the base's defaults. To give it values of its own, see
    [Give a cluster its own values](../../how-to/cluster-values.md#give-a-cluster-its-own-values). Don't set
    `global.release.version` in them, because the chart sets it. For another provider, see
    [Create a cluster base for a provider other than CAPA](../../how-to/cluster-base-provider.md).

1. Create the cluster's list of apps. It starts empty, and you add an app to it in the next step. First, create its
   directory:

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

    Then list it in `${WC_DIR}/kustomization.yaml`. That file leaves out `cluster`, as the cluster has a
    `Kustomization` of its own:

    ```sh
    cat <<'EOF' > ${WC_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - apps/
    EOF
    ```

1. Create the cluster's `Kustomization`. It goes in the organisation's `workload-clusters`, next to the cluster's
   directory. The organisation's namespace `Kustomization` applies it into `org-${ORG_NAME}`, where it runs as that
   namespace's `automation` ServiceAccount and reads your `GitRepository` in `default`. Its `dependsOn` names the
   organisation's namespace `Kustomization`, so that one always applies a commit first. Its health check waits until
   Cluster API reports the cluster `Available`, which can take up to its `timeout` of 30 minutes.

    With `prune: true`, Flux deletes whatever you delete from the cluster's files, except the cluster itself: the
    cluster's `HelmRelease`, from the CAPA cluster base, has the `kustomize.toolkit.fluxcd.io/prune: disabled`
    annotation and the `giantswarm.io/prevent-deletion` label. The `# renovate:` comment lets
    [Renovate](https://docs.renovatebot.com/) propose new releases, if your fork uses it:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml
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
          # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
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

1. Create the apps' `Kustomization`. It names the cluster's `Kustomization` in `dependsOn`, so Flux applies none of it
   until the cluster's is `Ready`:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${WC_NAME}-apps.yaml
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
          # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
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

    Add both to the organisation's list of clusters:

    ```sh
    yq -i '.resources |= ((. // []) + ["'"${WC_NAME}"'.yaml", "'"${WC_NAME}"'-apps.yaml"] | unique)' \
      ${ORG_DIR}/workload-clusters/kustomization.yaml
    ```

1. Commit and push:

    ```sh
    git add ${ORG_DIR} && git commit -m "Add workload cluster ${WC_NAME}" && git push
    ```

**Check:** the cluster takes 15 to 20 minutes to come up, which is long enough for a cup of tea. Watch it with:

```sh
kubectl gs get clusters -n org-${ORG_NAME}
```

Once it's up, the cluster's `Kustomization` is `Ready`, and the apps' `Kustomization` follows:

```sh
flux get kustomizations -n org-${ORG_NAME} | grep ${MC_NAME}-clusters-${WC_NAME}
```

Log in to the cluster:

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

An app is two Flux objects on the management cluster: an `OCIRepository` that points at a Helm chart, and a
`HelmRelease` that installs it into the workload cluster, reaching the cluster through its `${cluster_name}-kubeconfig`
Secret. Here you deploy the [hello-world](https://github.com/giantswarm/hello-world-app) chart, with some values in
Git and one secret value from the organisation's store.

> **Shortcut:** [`kubectl gs deploy chart`](https://docs.giantswarm.io/reference/kubectl-gs/deploy-chart/) with
> `--dry-run` writes the `OCIRepository` and the `HelmRelease`. See [App](../../how-to/kubectl-gs.md#app) for the
> command. Never run it without `--dry-run` here: it would apply them to the management cluster directly, behind
> Git's back.

1. Save the app's directory for the next commands, and create it:

    ```sh
    export APP_DIR=${WC_DIR}/apps/hello-world
    mkdir -p ${APP_DIR}
    ```

1. Create the `OCIRepository`, which names the chart and its version. `3.2.2` is the version this repository's
   examples pin as this is written; any published version works. Renovate finds a `tag` in an `OCIRepository` by
   itself, if your fork uses it:

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
        tag: 3.2.2
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
          name: ${cluster_name}-hello-world-user-values
          valuesKey: values
        - kind: Secret
          name: ${cluster_name}-hello-world-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

    The chart's values come in layers, and later ones win. The `${cluster_name}-cluster-values` ConfigMap, which the
    management cluster creates for every workload cluster, gives the chart values such as `baseDomain`. Your values in
    Git come next, and the secret values last. The Secret is `optional`, as it doesn't exist until ESO writes it:
    Flux installs the chart without it, and upgrades the release as soon as it appears. For every layer an app can
    have, see [App values](../../reference/values.md#app-values).

1. Put the app's values in `override_config.yaml`:

    ```sh
    cat <<'EOF' > ${APP_DIR}/override_config.yaml
    ingress:
      enabled: false
    EOF
    ```

1. Create the `ExternalSecret`, which has ESO read the app's secret values from the store and write them into the
   `${cluster_name}-hello-world-user-secrets` Secret the `HelmRelease` reads. The hello-world chart has no secret
   settings, so the stand-in store from step 2 holds a pod annotation instead: the plumbing is the same either way.
   The label has Flux upgrade the release as soon as the Secret changes. The backslashes keep `${cluster_name}` and
   `${organization}` for Flux to fill in:

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
        kind: SecretStore
        name: ${SECRET_STORE}
      target:
        name: \${cluster_name}-hello-world-user-secrets
        template:
          metadata:
            labels:
              reconcile.fluxcd.io/watch: Enabled
      data:
        - secretKey: values
          remoteRef:
            key: gitops/hello-world-values
    EOF
    ```

    With your own secret manager, store the values there, as YAML, and put the name of that secret in `key`. If the
    secret holds several fields, add `property: FIELD_NAME` under `remoteRef`.

1. Create the app's `kustomization.yaml`. Its `configMapGenerator` turns `override_config.yaml` into the ConfigMap the
   `HelmRelease` reads, and the label has Flux upgrade the release as soon as you change it:

    ```sh
    cat <<'EOF' > ${APP_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: org-${organization}
    configMapGenerator:
      - name: ${cluster_name}-hello-world-user-values
        files:
          - values=override_config.yaml
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    resources:
      - oci-repository.yaml
      - helm-release.yaml
      - externalsecret.yaml
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

**Check:** the `ExternalSecret` reports `SecretSynced`:

```sh
kubectl get externalsecret ${WC_NAME}-hello-world-user-secrets -n org-${ORG_NAME}
```

The release is `Ready` on the management cluster:

```sh
flux get helmreleases ${WC_NAME}-hello-world -n org-${ORG_NAME}
```

The pods run in the workload cluster, with the annotation from the store:

```sh
kubectl --context ${WC_CONTEXT} get pods -n hello-world \
  -o custom-columns='NAME:.metadata.name,SOURCE:.metadata.annotations.example\.com/source'
```

Learn more:
[Deploying an app with a Flux HelmRelease](https://docs.giantswarm.io/tutorials/fleet-management/app-platform/deploy-app-helmrelease/).

## 5. Update the app

You update an app the way you deployed it: change its files and push. First, upgrade the chart to a newer version,
for example `3.2.3`:

```sh
yq -i '.spec.ref.tag = "3.2.3"' ${APP_DIR}/oci-repository.yaml
```

Next, change a value, so that at least two replicas run:

```sh
yq -i '.autoscaling.minReplicas = 2' ${APP_DIR}/override_config.yaml
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

Secret values don't change in the app's files, so you change them in your secret manager. With the stand-in store
from step 2, that's its file in `multicluster/secret-stores`, which you commit and push. ESO copies a change within the
`ExternalSecret`'s `refreshInterval`, and Flux upgrades the release as soon as the Secret changes. To have ESO copy it
straight away:

```sh
kubectl annotate externalsecret ${WC_NAME}-hello-world-user-secrets -n org-${ORG_NAME} \
  force-sync=$(date +%s) --overwrite
```

To have Flux install new chart versions by itself, replace `tag` with a `semver` range in the `OCIRepository`. For
example, `semver: 3.2.x` installs every new patch version. See
[Automatic updates](../intermediate/automatic-updates.md).

## 6. Delete the cluster (optional)

Skip this step to keep the cluster. Deleting a cluster is deliberately awkward, and this step shows you why.

When you delete the cluster's files, Flux deletes its `Kustomization`s, its apps and its configuration, but not the
cluster itself. Its `HelmRelease` has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, so Flux leaves it
in place, and the `giantswarm.io/prevent-deletion` label, so nobody can delete it until the label is gone. Its
`OCIRepository` has both too, and its `Cluster` has the label. So you take the labels off first, and delete the
`HelmRelease` and the `OCIRepository` yourself at the end. If kubectl-gs wrote your cluster's files, check what it
protects first: kubectl-gs 7.0.0 and newer label the cluster's `HelmRelease` and `OCIRepository`, but no release
writes the annotation or protects the `Organization`, see
[What kubectl-gs writes](../../explanation/deletion-protection.md#what-kubectl-gs-writes).

These steps delete the cluster this tutorial created. A cluster with its own SOPS key in `namespace/secrets`,
out-of-band resources or an application team needs more, see
[Delete a workload cluster](../../how-to/delete-cluster.md).

1. Remove the label from the cluster's `OCIRepository` and `HelmRelease`, and set `global.metadata.preventDeletion`
   to `false`, so that the chart removes the label from the cluster's `Cluster` too:

    ```sh
    yq -i '.patches += [{"patch": "[{\"op\": \"remove\", \"path\": \"/metadata/labels/giantswarm.io~1prevent-deletion\"}]", "target": {"labelSelector": "giantswarm.io/prevent-deletion"}}, {"patch": "{\"apiVersion\": \"helm.toolkit.fluxcd.io/v2\", \"kind\": \"HelmRelease\", \"metadata\": {\"name\": \"cluster\"}, \"spec\": {\"values\": {\"global\": {\"metadata\": {\"preventDeletion\": false}}}}}", "target": {"kind": "HelmRelease"}}]' ${WC_DIR}/cluster/kustomization.yaml
    ```

    `spec.values` takes precedence over the ConfigMaps in `valuesFrom`, so this works whatever values the cluster
    has. Commit and push, then have Flux read the change straight away, one `Kustomization` after the other:

    ```sh
    git commit -am "Remove the deletion protection of workload cluster ${WC_NAME}" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-organization-${ORG_NAME} -n default
    flux reconcile kustomization ${MC_NAME}-clusters-${WC_NAME} -n org-${ORG_NAME}
    ```

    Then wait until the `Cluster` has lost the label, which takes an upgrade of the chart. The `PREVENT-DELETION`
    column has to be empty:

    ```sh
    kubectl get clusters.cluster.x-k8s.io ${WC_NAME} -n org-${ORG_NAME} -L giantswarm.io/prevent-deletion
    ```

1. Take the cluster's two `Kustomization`s out of the organisation's list, and remove their files and the cluster's
   directory. Then commit and push it all in one go:

    ```sh
    yq -i 'del(.resources[] | select(. == "'"${WC_NAME}"'.yaml" or . == "'"${WC_NAME}"'-apps.yaml"))' \
      ${ORG_DIR}/workload-clusters/kustomization.yaml
    git rm -q ${ORG_DIR}/workload-clusters/${WC_NAME}.yaml ${ORG_DIR}/workload-clusters/${WC_NAME}-apps.yaml
    git rm -rq ${WC_DIR}
    git commit -am "Delete workload cluster ${WC_NAME}" && git push
    ```

1. Have Flux read the change straight away:

    ```sh
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-organization-${ORG_NAME} -n default
    ```

    Flux deletes the cluster's `Kustomization`s, which delete the cluster's apps and configuration first. Wait until
    they're gone:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME} \
      kustomization/${MC_NAME}-clusters-${WC_NAME}-apps -n org-${ORG_NAME} --timeout=10m
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

The organisation, its secret store and the management cluster's connection to the repository stay, ready for the
next cluster.

## Next steps

You've built the whole path once, from a commit to an app on a cluster. The intermediate tutorials build on it:

- Reuse an app's configuration across clusters: [App Templates](../intermediate/app-templates.md).
- Deploy several apps together: [Stacks](../intermediate/stacks.md).
- Share cluster defaults through a base: [Cluster bases](../intermediate/cluster-bases.md).
- Run dev, staging and production clusters in several regions:
  [Stages and regions](../intermediate/stages-and-regions.md).
- Let Flux install new chart versions: [Automatic updates](../intermediate/automatic-updates.md).

To understand what you've built:

- What happens between a push and a running cluster: [How it works](../../explanation/how-it-works.md).
- Which secret goes where, with SOPS, ESO or both: [Secrets](../../explanation/secrets.md).
- Every directory and file, and the rules for them: [Repository structure](../../reference/repo-structure.md).

Everything else is on the [documentation home](../../README.md).

[github-token]: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token
