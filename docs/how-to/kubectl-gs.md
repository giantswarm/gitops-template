# Let kubectl-gs write the files

[`kubectl gs gitops`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/) writes the files of a management
cluster, an organisation, a workload cluster or an app for you, in the names this repository uses. It's a quick start,
not the finished article: every command writes the layout of structure version 2, and this repository uses version 3,
see [Structure version](../reference/repo-structure.md#structure-version). This page lists, command by command, what
it writes and what you change afterwards. For which files no command writes, see
[What kubectl-gs writes](../reference/repo-structure.md#what-kubectl-gs-writes).

The commands below need kubectl-gs 6.0.0 or newer, and 7.0.0 for the cluster's deletion protection, see
[kubectl-gs version](../reference/tools.md#kubectl-gs-version). Run them from the root of your clone. Pass `--dry-run`
to see what a command would write first. `kubectl gs gitops init` creates `.gitops-metadata.yaml` and `.sops.yaml` in a
new repository, and a Git `pre-commit` hook that refuses `*.enc.yaml` files `sops` hasn't encrypted; a fork of this
template has the files already.

## Management cluster

```sh
kubectl gs gitops add management-cluster --name ${MC_NAME} --repository-name ${GITOPS_REPO} --gen-master-key
```

It writes:

- `management-clusters/MC_NAME/MC_NAME.yaml`, the management cluster's `Kustomization`, `MC_NAME-gitops`, in
  `default`, decrypting with `sops-gpg-master`;
- an empty `management-clusters/MC_NAME/organizations`;
- with `--gen-master-key`, a new master key: its public key in `.sops.keys/master.FINGERPRINT.asc`, its private key in
  `secrets/MC_NAME.gpgkey.enc.yaml`, *not yet encrypted*, and a rule in `.sops.yaml` that encrypts
  `MC_NAME/secrets` with it.

With `--skip-encryption` instead, it leaves out the master key, the `secrets` and `.sops.keys` directories and the
`decryption`, for a repository that keeps no secrets in Git, see [Secrets](../explanation/secrets.md).

Pass `--gen-master-key` only for a management cluster without a master key: check with
`kubectl get secret sops-gpg-master -n default` first. Replacing an existing one leaves Flux unable to decrypt anything
encrypted for the old key.

Then change:

1. In `MC_NAME.yaml`, set `prune: true`, `interval: 10m` and `retryInterval: 1m`. The command writes `prune: false`, so
   Flux would never delete what you delete from Git:

    ```sh
    yq -i '.spec.prune = true | .spec.interval = "10m" | .spec.retryInterval = "1m"' \
      management-clusters/${MC_NAME}/${MC_NAME}.yaml
    ```

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

    Then protect the Secret with a `secrets/kustomization.yaml`, as the basic tutorial does.

1. Add the `.sops.yaml` rule for the workload clusters' keys in the organisations' `namespace/secrets`, which the
   command doesn't write, see [SOPS keys](../reference/sops-keys.md#encryption-rules).

The `GitRepository` and the repository token aren't in the repository: you create them on the management cluster once,
as the basic tutorial does.

## Organisation

```sh
kubectl gs gitops add organization --name ${ORG_NAME} --management-cluster ${MC_NAME}
```

It writes the `Organization` in `organizations/ORG_NAME/ORG_NAME.yaml`, and an empty
`organizations/ORG_NAME/workload-clusters/kustomization.yaml`, the organisation's list of clusters.
`kubectl gs template organization --name ${ORG_NAME}` prints the same `Organization`.

Then change:

1. Protect the `Organization`. Deleting it deletes the organisation's namespace with every cluster in it, and no
   release of kubectl-gs writes the protection, see [Deletion protection](../explanation/deletion-protection.md):

    ```sh
    yq -i '.metadata.annotations["kustomize.toolkit.fluxcd.io/prune"] = "disabled" |
      .metadata.labels["giantswarm.io/prevent-deletion"] = "true"' \
      management-clusters/${MC_NAME}/organizations/${ORG_NAME}/${ORG_NAME}.yaml
    ```

1. Add what no command writes: the organisation's namespace `Kustomization`, `namespace.yaml`, its `namespace`
   directory, which lists `../workload-clusters`, and the organisation's `kustomization.yaml` with the replacements
   that set its name, as in the
   [basic tutorial](../tutorials/basic/getting-started.md#2-add-an-organisation). Leave `workload-clusters` out of the
   organisation's `kustomization.yaml`: the organisation's namespace `Kustomization` applies it.

## Workload cluster

```sh
kubectl gs gitops add workload-cluster --name ${WC_NAME} --organization ${ORG_NAME} \
  --management-cluster ${MC_NAME} --repository-name ${GITOPS_REPO} \
  --base bases/clusters/capa --release ${RELEASE_VERSION} --skip-mapi \
  --cluster-user-config values.yaml
```

`--skip-mapi` puts `cluster` and `apps` straight into the cluster's directory, as this repository does. Without it,
they go into a `mapi` directory. `--cluster-user-config` takes a file of values, and is optional. It writes:

- `workload-clusters/WC_NAME.yaml`, one `Kustomization`, `MC_NAME-clusters-WC_NAME`, in `default`, that applies the
  whole cluster directory, with `prune: false`, `interval: 1m`, and the organisation's name written out, and lists it
  in `workload-clusters/kustomization.yaml`;
- `WC_NAME/cluster/kustomization.yaml`, which lists the base, with the deprecated `commonLabels`;
- with `--cluster-user-config`, `cluster/cluster_userconfig.yaml` and `cluster/patch_cluster_userconfig.yaml`, with
  the cluster's name written out and no `reconcile.fluxcd.io/watch` label;
- `WC_NAME/apps/kustomization.yaml`, empty, with `commonLabels`.

Then change:

1. Without `--skip-mapi`, move what's in `mapi` up into the cluster's directory, and take one `../` off the path to
   the base, which the command writes for `mapi/cluster`:

    ```sh
    export WC_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}
    mv ${WC_DIR}/mapi/apps ${WC_DIR}/mapi/cluster ${WC_DIR}/ && rmdir ${WC_DIR}/mapi
    yq -i '.resources |= map(sub("^\.\./"; ""))' ${WC_DIR}/cluster/kustomization.yaml
    ```

1. Add the cluster's region. The command doesn't, and a cluster without one is created in the management cluster's
   region, see [Regions](../tutorials/intermediate/stages-and-regions.md#regions):

    ```sh
    export REGION=eu_central
    yq -i '.components = ["../../../../../../../bases/environments/regions/" + strenv(REGION)]' \
      ${WC_DIR}/cluster/kustomization.yaml
    ```

1. Move the `commonLabels` of both `kustomization.yaml`s under `labels:`, as one `- pairs:` entry, to match the
   examples. `kustomize edit fix` converts them too, but also sets `includeSelectors: true`:

    ```sh
    for f in ${WC_DIR}/cluster/kustomization.yaml ${WC_DIR}/apps/kustomization.yaml; do
      yq -i '.labels = [{"pairs": .commonLabels}] | del(.commonLabels)' ${f}
    done
    ```

1. With `--cluster-user-config`, give the values ConfigMap the `reconcile.fluxcd.io/watch` label, which CI requires,
   and use the variables for its name and namespace, as
   [Give a cluster its own values](./cluster-values.md#give-a-cluster-its-own-values) does:

    ```sh
    yq -i '.metadata.labels["reconcile.fluxcd.io/watch"] = "Enabled" |
      .metadata.name = "${cluster_name}-cluster-userconfig" | .metadata.namespace = "org-${organization}"' \
      ${WC_DIR}/cluster/cluster_userconfig.yaml
    yq -i '.[0].value.name = "${cluster_name}-cluster-userconfig"' ${WC_DIR}/cluster/patch_cluster_userconfig.yaml
    ```

1. Add `${WC_DIR}/kustomization.yaml`, which lists `apps/` and leaves out `cluster` and `out-of-band`:

    ```sh
    cat <<'EOF' > ${WC_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - apps/
    EOF
    ```

1. Replace `WC_NAME.yaml` with the cluster's two `Kustomization`s, `WC_NAME.yaml` for `cluster` and `WC_NAME-apps.yaml`
   for the rest, as in the
   [basic tutorial](../tutorials/basic/getting-started.md#3-create-a-workload-cluster), and list both in
   `workload-clusters/kustomization.yaml`. They need what the command leaves out: no namespace, as the organisation's
   namespace `Kustomization` puts them in the organisation's; `sourceRef.namespace: default`;
   `organization: "${organization}"`; the organisation's namespace `Kustomization` in `dependsOn`; `prune: true`; and
   the `Cluster` health check. See [Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations) for why.
   The `-apps` suffix is only the template's label for the second one, not a convention: name it however you like, see
   [Naming](../reference/repo-structure.md#naming).

1. If the cluster needs SOPS-encrypted files, add its key as
   [Add a workload cluster key (GPG)](./sops.md#add-a-workload-cluster-key-gpg) describes. Don't use
   `kubectl gs gitops add encryption --workload-cluster`: it writes the key Secret into `MC_NAME/secrets`, in
   `default`, where the cluster's `Kustomization`s can't read it.

`kubectl gs gitops add base --provider capa` writes the base into `bases/clusters/capa/template`, not
`bases/clusters/capa`. Move its files up a level, and add the management cluster's values, see
[Write the base](./cluster-base-provider.md#write-the-base).

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
  --workload-cluster ${WC_NAME} --skip-mapi
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
  --management-cluster ${MC_NAME} --organization ${ORG_NAME} --workload-cluster ${WC_NAME} --skip-mapi
```

It replaces `spec.ref.tag` with `spec.ref.semver` in `apps/APP_NAME/oci-repository.yaml`, so Flux installs the highest
version in the range. Without `--skip-mapi` it looks for the app in `mapi/apps`, and finds nothing in this layout.
`--version-range` defaults to `>=0.0.0`, any version.

It only changes an app with its own `oci-repository.yaml`. For an app from an App Template or a stack, patch the
template's `OCIRepository` in the app's `kustomization.yaml` instead, and for a base app in `cluster/apps`, edit the
file by hand. See [Let Flux install new chart versions](../tutorials/intermediate/automatic-updates.md).
