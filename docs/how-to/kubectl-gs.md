# Let kubectl-gs write the files

[`kubectl gs gitops`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/) writes the files of a management
cluster, an organisation, a workload cluster or an app for you, in the layout and the names this repository uses,
structure version 3, see [Structure version](../reference/repo-structure.md#structure-version). It's a quick start,
not the finished article: this page lists, command by command, what it writes and the little it leaves to you. For the
files no command writes, see [What kubectl-gs writes](../reference/repo-structure.md#what-kubectl-gs-writes).

The commands below need kubectl-gs X.Y.Z or newer, see [kubectl-gs version](../reference/tools.md#kubectl-gs-version).
Older releases write structure version 2, with a `mapi` directory, which
[Bring an older fork up to date](./upgrade-fork.md) moves on. Run them from the root of your clone, and pass
`--dry-run` to see what a command would write first. `kubectl gs gitops init` creates `.gitops-metadata.yaml` and
`.sops.yaml` in a new repository, and a Git `pre-commit` hook that refuses `*.enc.yaml` files `sops` hasn't encrypted;
a fork of this template has the files already.

## Management cluster

```sh
kubectl gs gitops add management-cluster --name ${MC_NAME} --repository-name ${GITOPS_REPO} --gen-master-key
```

It writes:

- `management-clusters/MC_NAME/MC_NAME.yaml`, the management cluster's `Kustomization`, `MC_NAME-gitops`, in
  `default`, with `prune: true`, decrypting with `sops-gpg-master`;
- an empty `management-clusters/MC_NAME/organizations`;
- with `--gen-master-key`, a new master key: its public key in `.sops.keys/master.FINGERPRINT.asc`, its private key in
  `secrets/MC_NAME.gpgkey.enc.yaml`, *not yet encrypted*, a `secrets/kustomization.yaml` that protects it from
  deletion, and two rules in `.sops.yaml`: one that encrypts `MC_NAME/secrets` with it, and one for the workload
  clusters' keys in the organisations' `namespace/secrets`.

With `--skip-encryption` instead, it leaves out the master key, the `secrets` and `.sops.keys` directories and the
`decryption`, for a repository that keeps no secrets in Git, see [Secrets](../explanation/secrets.md).

Pass `--gen-master-key` only for a management cluster without a master key: check with
`kubectl get secret sops-gpg-master -n default` first. Replacing an existing one leaves Flux unable to decrypt anything
encrypted for the old key.

Then:

1. With a master key, the private key is only in `secrets/MC_NAME.gpgkey.enc.yaml`, unencrypted, under the key
   `master.FINGERPRINT.asc`: kubectl-gs made it in memory and never put it in your keyring. Rename its public key to
   the name the docs use, and import the private key from the Secret:

    ```sh
    export MC_DIR=management-clusters/${MC_NAME}
    export KEY_FP=$(basename ${MC_DIR}/.sops.keys/master.*.asc .asc | sed 's/^master\.//')
    mv ${MC_DIR}/.sops.keys/master.${KEY_FP}.asc ${MC_DIR}/.sops.keys/.sops.master.asc
    yq ".data[\"master.${KEY_FP}.asc\"]" ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml | base64 -d | gpg --import
    ```

1. Save the private key in your password manager now, with `KEY_FP` set as above and
   `ITEM="GPG private key (${MC_NAME}, master, Flux)"`, see
   [Keep a private key in a password manager](./sops.md#keep-a-private-key-in-a-password-manager). Once the file is
   encrypted and the key is gone from your keyring, the password manager holds the only copy you can read.

1. Apply the Secret, so that Flux has `sops-gpg-master` in `default` before it needs it, then encrypt the file with
   the rule kubectl-gs wrote, and delete the private key from your keyring. This is the order the
   [basic tutorial](../tutorials/basic/getting-started.md#1-connect-the-management-cluster) uses: the file holds the
   private key in plain text until `sops` has encrypted it, so don't add it to Git before then.

    ```sh
    kubectl apply -f ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml
    sops --encrypt --in-place ${MC_DIR}/secrets/${MC_NAME}.gpgkey.enc.yaml
    gpg --batch --yes --delete-secret-keys "${KEY_FP}"
    ```

`MC_NAME.yaml` has no `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. It applies itself, so renaming it
would make Flux prune it, and its finalizer would delete everything beneath it, see
[Deletion protection](../explanation/deletion-protection.md#the-protected-objects). Add the annotation, as the
template's has it:

```sh
yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled"' ${MC_DIR}/${MC_NAME}.yaml
```

`MC_NAME.yaml` has `interval: 1m` and no `retryInterval`. The template uses `interval: 10m` and `retryInterval: 1m`,
see [Reconcile intervals](../reference/repo-structure.md#reconcile-intervals); either works. The `GitRepository` and
the repository token aren't in the repository: you create them on the management cluster once, as the basic tutorial
does.

## Organisation

```sh
kubectl gs gitops add organization --name ${ORG_NAME} --management-cluster ${MC_NAME}
```

It writes what [step 2](../tutorials/basic/getting-started.md#2-add-an-organisation) of the basic tutorial writes by
hand:

- the `Organization`, in `organizations/ORG_NAME/ORG_NAME.yaml`, with the `kustomize.toolkit.fluxcd.io/prune: disabled`
  annotation and the `giantswarm.io/prevent-deletion` label, see [Deletion protection](../explanation/deletion-protection.md);
- the organisation's namespace `Kustomization`, `namespace.yaml`, which reads the `GitRepository` of `MC_NAME.yaml`
  unless you pass `--repository-name`;
- the organisation's `kustomization.yaml`, which lists those two and sets the organisation's name in them, see
  [The organisation's name](../reference/repo-structure.md#the-organisations-name);
- `namespace/kustomization.yaml`, which lists `../workload-clusters`, and an empty
  `workload-clusters/kustomization.yaml`, the organisation's list of clusters.

One thing to change: `namespace.yaml` has no `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, and without
it a rename or a dropped line would make Flux prune it and uninstall every app in the organisation. Add it:

```sh
yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled"' \
  management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace.yaml
```

`kubectl gs template organization --name ${ORG_NAME}` prints the `Organization` alone,
without the protection.

## Workload cluster

```sh
kubectl gs gitops add workload-cluster --name ${WC_NAME} --organization ${ORG_NAME} \
  --management-cluster ${MC_NAME} --repository-name ${GITOPS_REPO} \
  --base bases/clusters/capa --release ${RELEASE_VERSION} \
  --cluster-user-config values.yaml
```

The organisation needs its `namespace.yaml`, and its clusters' `Kustomization`s in its namespace: the command refuses
an organisation that hasn't moved them yet, and links to
[Move the workload cluster Kustomizations](./upgrade-fork.md#move-the-workload-cluster-kustomizations).
`--cluster-user-config` takes a file of values, and is optional. It writes:

- with `--base`, the cluster's two `Kustomization`s, `WC_NAME.yaml`, `MC_NAME-clusters-WC_NAME`, which applies
  `cluster` and waits for the Cluster API `Cluster` to be `Available`, and `WC_NAME-apps.yaml`, which applies the rest
  once it is, and lists both in `workload-clusters/kustomization.yaml`. They have no namespace, so the organisation's
  namespace `Kustomization` puts them in the organisation's, `prune: true`, and the organisation's namespace
  `Kustomization` in `dependsOn`, see [Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations).
  Without `--base`, there's only `WC_NAME.yaml`, which applies the apps;
- `WC_NAME/kustomization.yaml`, which lists `apps/`, and never `cluster` or `out-of-band`;
- `WC_NAME/cluster/kustomization.yaml`, which lists the base;
- with `--cluster-user-config`, `cluster/cluster_userconfig.yaml` and `cluster/patch_cluster_userconfig.yaml`;
- `WC_NAME/apps/kustomization.yaml`, with no apps yet.

Then:

1. Add the cluster's region. The command doesn't, and a cluster without one is created in the management cluster's
   region, see [Regions](../tutorials/intermediate/stages-and-regions.md#regions):

    ```sh
    export WC_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}
    export REGION=eu_central
    yq -i '.components = ["../../../../../../../bases/environments/regions/" + strenv(REGION)]' \
      ${WC_DIR}/cluster/kustomization.yaml
    ```

1. With `--cluster-user-config`, give the values ConfigMap the `reconcile.fluxcd.io/watch` label, which CI requires,
   and use the variables for its name and namespace, as
   [Give one cluster its own values](./cluster-values.md#write-the-clusters-values-configmap) does. The command writes
   the cluster's and the organisation's names out:

    ```sh
    yq -i '.metadata.labels["reconcile.fluxcd.io/watch"] = "Enabled" |
      .metadata.name = "${cluster_name}-cluster-userconfig" | .metadata.namespace = "org-${organization}"' \
      ${WC_DIR}/cluster/cluster_userconfig.yaml
    yq -i '.[0].value.name = "${cluster_name}-cluster-userconfig"' ${WC_DIR}/cluster/patch_cluster_userconfig.yaml
    ```

1. If the cluster needs SOPS-encrypted files, give it a key, see
   [Add a workload cluster key (GPG)](./sops.md#add-a-workload-cluster-key-gpg), or let
   `kubectl gs gitops add encryption --workload-cluster ${WC_NAME}` write it, as below.

1. Make the cluster's `Kustomization` wait for the control plane rather than for `Available`, which counts every node
   pool, so that one short node pool doesn't hold back every change to the cluster's apps. Take its health check from
   the example, see [Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations):

    ```sh
    export WC_FILE=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}.yaml
    yq -i ".spec.healthCheckExprs = $(yq -o json '.spec.healthCheckExprs' \
      management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml)" ${WC_FILE}
    ```

A few things differ from the examples, and are yours to keep or change. The `kustomization.yaml`s use
`commonLabels`, which kustomize has deprecated in favour of `labels:`; `kustomize edit fix` converts them. The
`Kustomization`s have `interval: 1m` and no `retryInterval`, where the template uses `10m` and `1m`. The `-apps`
suffix is the command's name for the second `Kustomization`, and the template's, but nothing depends on it, see
[Naming](../reference/repo-structure.md#naming).

`kubectl gs gitops add base --provider capa` writes the base into `bases/clusters/capa`, the path `--base` takes. Add
the management cluster's values to it, see [Write the base](./cluster-base-provider.md#write-the-base).

### Encryption

```sh
kubectl gs gitops add encryption --generate --management-cluster ${MC_NAME} \
  --organization ${ORG_NAME} --workload-cluster ${WC_NAME} --target apps/
```

It generates a GPG key for the cluster and writes its private key, *not yet encrypted*, into
`namespace/secrets/WC_NAME.gpgkey.enc.yaml`, as the Secret `sops-gpg-WC_NAME`, in the organisation's namespace, where
the cluster's `Kustomization`s run. It lists the file in a protected `namespace/secrets/kustomization.yaml`, gives
both of the cluster's `Kustomization`s the `decryption`, puts the public key in `.sops.keys`, and adds a rule to
`.sops.yaml` for the directory `--target` names, `secrets/` in the cluster's directory unless you say otherwise. It
needs the master key's rule in `.sops.yaml`, which encrypts the new key.

Then encrypt the key file with `sops --encrypt --in-place`, before you add it to Git, and save the private key in your
password manager, as in [Add a workload cluster key (GPG)](./sops.md#add-a-workload-cluster-key-gpg). The command
makes GPG keys only; for an age key, follow
[Add a workload cluster key (age)](./sops.md#add-a-workload-cluster-key-age).

## App

An app's `HelmRelease` in this template reads the cluster's values first, then the optional `-user-values` ConfigMap
and `-user-secrets` Secret, with `${cluster_name}` in every name, so the same files work for any cluster. The cluster
values give the chart what only the management cluster knows about the cluster, such as its `baseDomain`, and as the
first layer, your values can override them, see [App values](../reference/values.md#app-values).

The apps come in two layouts, and [Add an app to a cluster](./add-app.md) describes both:

- **Files listed one by one.** The app's directory holds only its manifests, and the cluster's `apps/kustomization.yaml`
  lists each file, as the `cert-manager`, `flux`, `hello-world` and `hello-world-automatic-updates` examples do. It
  fits an app written out in full, whose values, if any, are a plain ConfigMap or Secret file next to it.
- **A `kustomization.yaml` of the app's own**, which the cluster's list names as a directory, as the
  `*-from-template` examples do. An app from an App Template or a stack needs it, to list the base and patch it, and
  so does an app whose values a `configMapGenerator` makes from `override_config.yaml`.

Two commands write an app, and neither writes the `HelmRelease` this template uses.

`kubectl gs gitops add app` is deprecated since kubectl-gs 5.2.0, without a replacement:

```sh
kubectl gs gitops add app --name ${APP_NAME} --app ${APP_CHART} --version ${APP_VERSION} \
  --target-namespace ${APP_NAMESPACE} --organization ${ORG_NAME} --management-cluster ${MC_NAME} \
  --workload-cluster ${WC_NAME}
```

It writes `apps/APP_NAME/oci-repository.yaml` and `helm-release.yaml`, and with `--user-configmap` or `--user-secret`,
a `configmap.yaml` or an unencrypted `secret.enc.yaml`, both named `WC_NAME-APP_NAME-user-values`. It lists the files
one by one in `apps/kustomization.yaml`, and writes no `kustomization.yaml` for the app: the first layout above. The
`HelmRelease` writes the cluster's name out, such as `demowc-hello-world` and `demowc-kubeconfig`, and its `valuesFrom`
has no cluster values. To get to the template's `HelmRelease`:

1. Change the names to `${cluster_name}-APP_NAME`, `${cluster_name}-kubeconfig` and the namespace to
   `org-${organization}`, so the files work for any cluster.
1. Set the `HelmRelease`'s `valuesFrom` to the three layers above.
1. Rename the ConfigMap in `configmap.yaml` to `${cluster_name}-APP_NAME-user-values`, and give it the
   `reconcile.fluxcd.io/watch: Enabled` label, which CI requires. Rename the Secret in `secret.enc.yaml` to
   `${cluster_name}-APP_NAME-user-secrets`, add the label and encrypt it, see
   [Encrypt an app's values](./sops.md#encrypt-an-apps-values).
1. Keep the files listed one by one. To keep the values in a plain `override_config.yaml` instead, switch to the second
   layout: replace `configmap.yaml` with a `kustomization.yaml` in the app's directory whose `configMapGenerator`
   makes the ConfigMap, and list the app's directory in `apps/kustomization.yaml` instead of its files, as
   [Add an app directly](./add-app.md#add-an-app-directly) does.

With `--base`, it writes a `kustomization.yaml` that lists the base, and a `patch_app_userconfig.yaml` that appends the
`-user-values` ConfigMap to the `HelmRelease`. The App Templates here list that layer already, so leave the patch out.

`kubectl gs deploy chart --dry-run` prints an `OCIRepository` and a `HelmRelease` for one chart, without writing a
file. Always pass `--dry-run`: without it, the command applies them to the management cluster directly, outside of Git.
It takes the `valuesFrom` entries with `--values-from`, so it can print the template's shape apart from the names:

```sh
kubectl gs deploy chart --chart-name ${APP_CHART} --version ${APP_VERSION} \
  --organization ${ORG_NAME} --target-cluster ${WC_NAME} --target-namespace ${APP_NAMESPACE} \
  --values-from ConfigMap/${WC_NAME}-cluster-values:values \
  --values-from ConfigMap/${WC_NAME}-${APP_NAME}-user-values:values:optional \
  --values-from Secret/${WC_NAME}-${APP_NAME}-user-secrets:values:optional \
  --dry-run | APP_DIR=${APP_DIR:?set APP_DIR to the app directory} \
  yq -s '.kind as $k | strenv(APP_DIR) + "/" +
    {"HelmRelease": "helm-release", "OCIRepository": "oci-repository"}[$k] + ".yaml"'
```

This writes `oci-repository.yaml` and `helm-release.yaml`. Change the names as for `gitops add app`, and list the
files in `apps/kustomization.yaml`, or add an app `kustomization.yaml` as in the second layout.

## Automatic updates

```sh
kubectl gs gitops add automatic-update --app ${APP_NAME} --version-range '>=1.2.0 <2.0.0' \
  --management-cluster ${MC_NAME} --organization ${ORG_NAME} --workload-cluster ${WC_NAME}
```

It replaces `spec.ref.tag` with `spec.ref.semver` in `apps/APP_NAME/oci-repository.yaml`, so Flux installs the highest
version in the range. `--version-range` defaults to `>=0.0.0`, any version.

It only changes an app with its own `oci-repository.yaml`, and refuses an app from a base. For an app from an App
Template or a stack, patch the template's `OCIRepository` in the app's `kustomization.yaml` instead, and for a base
app in `cluster/apps`, edit the file by hand. See [Let Flux install new chart versions](../tutorials/intermediate/automatic-updates.md).
