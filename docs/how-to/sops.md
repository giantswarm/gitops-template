# Keep secrets in the repository

[SOPS](https://github.com/getsops/sops) encrypts the values of a Secret in a file, so you can commit the file, and Flux
decrypts it when it applies it. This page covers the keys and the files: adding a key for a workload cluster or an
organisation, encrypting an app's values, and changing them later. For which keys exist and what each one decrypts, see
[SOPS keys](../reference/sops-keys.md); for when to use SOPS rather than a secret manager, see
[Secrets](../explanation/secrets.md).

You need:

- `gpg`, `sops` 3.10.0 or newer and `yq`, and `age-keygen` for an age key, see [Tools](../reference/tools.md#tools);
- the management cluster's master key, which the
  [basic tutorial](../tutorials/basic/getting-started.md#1-connect-the-management-cluster) creates: its public key in
  `management-clusters/MC_NAME/.sops.keys/.sops.master.asc` and its private key in the `sops-gpg-master` Secret;
- the `.sops.yaml` rule that encrypts the workload clusters' keys with the master key, from the same step.

Export the names the commands use, and run them from the root of your clone:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export ORG_SECRETS=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/secrets
```

Every private key you create here ends up in two places: encrypted in the repository, for Flux, and in a password
manager, for you. Never commit one unencrypted, and delete it from your keyring when you're done.

The commands encrypt a Secret on its way into its file: they pipe it into `sops --encrypt`, and
`--filename-override` tells `sops` which file it's writing, and so which rule of `.sops.yaml` applies. Nothing sits in
the repository in plain text, not even for a minute. If `sops` can't encrypt, it says why, and the file it leaves
behind holds no secret. The [check-sops-encrypted](/tools/README.md#check-sops-encrypted) pre-commit hook fails for a
`*.enc.yaml` file that isn't encrypted, should one slip through anyway.

## Add a workload cluster key (GPG)

A key of the cluster's own keeps its secrets apart from other clusters': the cluster's key can decrypt its files, and
nothing else. Its private key goes into a Secret in the organisation's `namespace/secrets` directory, so it lands in the
organisation's namespace with the cluster's Flux `Kustomization`s that decrypt with it. The master key encrypts that
Secret.

> [!Note]
> From kubectl-gs 8.0.0 on, `kubectl gs gitops add encryption --workload-cluster` does most of these steps for you,
> see [Encryption](./kubectl-gs.md#encryption): the key Secret in `namespace/secrets`, its protection, the
> `decryption` of both `Kustomization`s, the public key and a `.sops.yaml` rule. Its rule covers only the directory
> `--target` names, the cluster's `secrets/` by default, so pass `--target apps/` or add a rule for `cluster` and
> `apps`, as in the last steps below; `--target /` covers the whole cluster directory, `out-of-band` included, where
> the cluster's key can't decrypt. You still encrypt the key and keep it in your password manager yourself. Older
> releases write the key into `MC_NAME/secrets`, where the cluster's `Kustomization`s can't read it: follow the steps
> below instead.

For more granular encryption, such as a key per app, see [Add another key to a cluster](#add-another-key-to-a-cluster):
a `Kustomization` reads one Secret, so every key of the cluster goes into the same one.

1. Generate a GPG key with no passphrase (`%no-protection`), as Flux has to use it unattended:

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
    export KEY_FP=$(gpg --list-secret-keys --with-colons "${KEY_NAME}" | awk -F: '/^fpr/{print $10; exit}')
    echo "${KEY_FP}"
    ```

1. The private key goes into a Kubernetes Secret in the organisation's `namespace/secrets` directory. If the
   organisation has no `namespace/secrets` yet, create it: its `kustomization.yaml` keeps Flux from deleting the keys,
   see [Deletion protection](../explanation/deletion-protection.md), and `namespace/kustomization.yaml` lists it:

    ```sh
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

1. Save the private key as a Kubernetes Secret into that directory, in the organisation's namespace, encrypted with
   the master GPG public key, which the first line imports. The management cluster's rule for the workload clusters'
   keys in `namespace/secrets` picks the master key. If your `.sops.yaml` doesn't have it, add it ahead of any rule of
   an organisation's own key for `namespace/secrets`, see [SOPS keys](../reference/sops-keys.md#encryption-rules):

    ```sh
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
    gpg --export-secret-keys --armor "${KEY_FP}" |
    kubectl create secret generic sops-gpg-${WC_NAME} \
    --dry-run=client \
    --namespace=org-${ORG_NAME} \
    --from-file=${WC_NAME}.main.asc=/dev/stdin \
    -o yaml |
    sops --encrypt --filename-override ${ORG_SECRETS}/${WC_NAME}.gpgkey.enc.yaml /dev/stdin \
    > ${ORG_SECRETS}/${WC_NAME}.gpgkey.enc.yaml
    ```

1. Add the new Secret to the resources of `${ORG_SECRETS}/kustomization.yaml`:

    ```sh
    yq -i ".resources += \"${WC_NAME}.gpgkey.enc.yaml\" | .resources style=\"\"" \
    ${ORG_SECRETS}/kustomization.yaml
    ```

1. Save the private key in your password manager, see
   [Keep a private key in a password manager](#keep-a-private-key-in-a-password-manager), then delete it from the
   keyring:

    ```sh
    gpg --delete-secret-keys "${KEY_FP}"
    ```

1. Share the new GPG public key in this repository:

    ```sh
    gpg --export --armor "${KEY_FP}" \
    > management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc
    ```

1. Add the rule that encrypts the cluster's files with its key to the [SOPS configuration file](/.sops.yaml). It covers
   `cluster` and `apps`, the directories the cluster's `Kustomization`s decrypt:

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
   the organisation's namespace `Kustomization` fails to build and stops reconciling:

    ```sh
    git add ${ORG_SECRETS} management-clusters/${MC_NAME}/organizations/${ORG_NAME}/namespace/kustomization.yaml \
    management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc \
    .sops.yaml
    git status --short management-clusters/${MC_NAME}
    ```

    `git status` should list no untracked file, marked `??`, under the management cluster.

Then tell the cluster's `Kustomization`s to use it, see [Decrypt a cluster's files](#decrypt-a-clusters-files).

### Add another key to a cluster

A cluster's `Kustomization`s read one key Secret, so a second key, for example one that only an app's files are
encrypted with, goes into the cluster's existing `WC_NAME.gpgkey.enc.yaml`, next to the first. Don't repeat the steps
above for it: they would replace the Secret and list it twice.

1. Give the key a name of its own, generate it as in the first two steps above, with `gpg --batch --full-generate-key`
   and `Name-Real: ${KEY_NAME}`, and keep its fingerprint:

    ```sh
    export KEY_NAME="${WC_NAME}-APP_NAME"
    ```

    ```sh
    export KEY_FP=$(gpg --list-secret-keys --with-colons "${KEY_NAME}" | awk -F: '/^fpr/{print $10; exit}')
    ```

1. Import the master private key from your password manager, see
   [Keep a private key in a password manager](#keep-a-private-key-in-a-password-manager), then add the new private key
   to the cluster's key Secret, as the [organisation key](#add-an-organisation-key) steps do with the master Secret.
   The Secret is decrypted only on its way through the pipe, and encrypted again into a new file that replaces the
   old one:

    ```sh
    export KEY_FILE=${ORG_SECRETS}/${WC_NAME}.gpgkey.enc.yaml
    (
    cat <<EOF
    data:
      ${KEY_NAME}.asc: $(gpg --export-secret-keys --armor "${KEY_FP}" | base64 | tr -d '\n')
    EOF
    ) | kubectl patch --local -f <(sops --decrypt ${KEY_FILE}) --patch-file=/dev/stdin -o yaml |
    sops --encrypt --filename-override ${KEY_FILE} /dev/stdin > ${KEY_FILE}.new &&
    mv ${KEY_FILE}.new ${KEY_FILE}
    ```

1. Share its public key, and put its rule ahead of the cluster's, so `sops` picks it for the files it covers:

    ```sh
    gpg --export --armor "${KEY_FP}" > management-clusters/${MC_NAME}/.sops.keys/.sops.${KEY_NAME}.asc
    yq -i '.creation_rules = [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/'"${ORG_NAME}"'/workload-clusters/'"${WC_NAME}"'/apps/APP_NAME/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }] + .creation_rules' .sops.yaml
    ```

1. Save the new private key in your password manager, delete it and the master key from your keyring, and commit
   the Secret, the public key and `.sops.yaml` together.

## Add a workload cluster key (age)

Instead of a GPG key, the cluster can have an [age](https://github.com/FiloSottile/age) key, which is simpler to
create and handle. [age or GPG](../reference/sops-keys.md#age-or-gpg) compares them. The master key stays a GPG key:
it encrypts the age key like it encrypts the GPG keys of other clusters. The example `WC_NAME` cluster uses one.

1. Generate the key. The file holds the private key, so keep it out of the repository:

    ```sh
    age-keygen -o ${WC_NAME}.agekey
    export AGE_PUBLIC_KEY=$(age-keygen -y ${WC_NAME}.agekey)
    ```

1. Save the private key as a Kubernetes Secret into the organisation's `namespace/secrets` directory, in the
   organisation's namespace, encrypted with the master key, which the management cluster's rule for the workload
   clusters' keys picks, as for the GPG key above. Create the directory first if the organisation doesn't have it.
   kustomize-controller reads age keys from Secret keys that end in `.agekey`:

    ```sh
    gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
    kubectl create secret generic sops-age-${WC_NAME} \
    --dry-run=client \
    --namespace=org-${ORG_NAME} \
    --from-file=${WC_NAME}.agekey=${WC_NAME}.agekey \
    -o yaml |
    sops --encrypt --filename-override ${ORG_SECRETS}/${WC_NAME}.agekey.enc.yaml /dev/stdin \
    > ${ORG_SECRETS}/${WC_NAME}.agekey.enc.yaml
    ```

1. Add it to the resources of `${ORG_SECRETS}/kustomization.yaml`:

    ```sh
    yq -i ".resources += \"${WC_NAME}.agekey.enc.yaml\" | .resources style=\"\"" \
    ${ORG_SECRETS}/kustomization.yaml
    ```

1. Save `${WC_NAME}.agekey` in your password manager, see
   [Keep a private key in a password manager](#keep-a-private-key-in-a-password-manager), then delete the file:

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
    git status --short management-clusters/${MC_NAME}
    ```

    `git status` should list no untracked file, marked `??`, under the management cluster.

The cluster's `Kustomization`s name `sops-age-${WC_NAME}` in `decryption.secretRef`, see
[Decrypt a cluster's files](#decrypt-a-clusters-files). A `Kustomization` reads one Secret: to use a GPG and an age
key for the same cluster, put both private keys into that one Secret.

## Add an organisation key

The management cluster's master key already encrypts the organisation's files. To keep one organisation's secrets
apart from another's, give it a key of its own. Its private key goes into the master Secret, `sops-gpg-master`, which
the organisation's namespace `Kustomization` decrypts with, so it can decrypt the files in the organisation's
`namespace`.

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
    export KEY_FP=$(gpg --list-secret-keys --with-colons "${KEY_NAME}" | awk -F: '/^fpr/{print $10; exit}')
    ```

1. Share the new GPG public key in this repository:

    ```sh
    gpg --export --armor "${KEY_FP}" \
    > management-clusters/${MC_NAME}/.sops.keys/.sops.${ORG_NAME}.asc
    ```

1. Configure the automatic key selection rule in the [SOPS configuration file](/.sops.yaml). `sops` uses the first rule
   that matches a file, so this rule has to come after the management cluster's rule for the workload clusters' SOPS
   keys in `namespace/secrets`, which encrypts them with the master key. `+=` appends it at the end of the list, after
   that rule. If your `.sops.yaml` doesn't have that rule yet, add it first, see
   [SOPS keys](../reference/sops-keys.md#encryption-rules):

    ```sh
    touch .sops.yaml
    yq -i '.creation_rules += [{
      "encrypted_regex": "^(data|stringData)$",
      "path_regex": "management-clusters/'"${MC_NAME}"'/organizations/'"${ORG_NAME}"'/namespace/secrets/.*\\.enc\\.yaml",
      "pgp": "'"${KEY_FP}"'"
    }]' .sops.yaml
    ```

1. Import the management cluster's master private key from your password manager into your keyring, see
   [Keep a private key in a password manager](#keep-a-private-key-in-a-password-manager).

1. Add the organisation's private key to the master Secret. The Secret is decrypted only on its way through the pipe,
   and encrypted again into a new file that replaces the old one:

    ```sh
    export MASTER_FILE=management-clusters/${MC_NAME}/secrets/${MC_NAME}.gpgkey.enc.yaml
    (
    cat <<EOF
    data:
      ${MC_NAME}.${ORG_NAME}.asc: $(gpg --export-secret-keys --armor "${KEY_FP}" | base64 | tr -d '\n')
    EOF
    ) | kubectl patch --local -f <(sops --decrypt ${MASTER_FILE}) --patch-file=/dev/stdin -o yaml |
    sops --encrypt --filename-override ${MASTER_FILE} /dev/stdin > ${MASTER_FILE}.new &&
    mv ${MASTER_FILE}.new ${MASTER_FILE}
    ```

1. Save the organisation's private key in your password manager, then delete the organisation's and the master
   private keys from the keyring:

    ```sh
    export MASTER_KEY_FP=$(gpg --show-keys --with-colons management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc |
    awk -F: '/^fpr/{print $10; exit}')
    gpg --delete-secret-keys "${KEY_FP}" "${MASTER_KEY_FP}"
    ```

1. Push the changes and wait for Flux to apply the master Secret. After that, Flux can decrypt the organisation's
   secrets.

1. Put a Secret into the organisation's `namespace/secrets`, which the organisation's namespace `Kustomization` applies
   into its namespace. Create the directory first if the organisation doesn't have it, as for a
   [workload cluster key](#add-a-workload-cluster-key-gpg), then list the file in its `kustomization.yaml`. Name the
   real namespace from the start: `org-${ORG_NAME}`, the one the namespace `Kustomization`'s `targetNamespace` sets.
   Changing the encrypted file afterwards breaks its MAC, and `sops` can then no longer decrypt it to change it or
   rotate its key. `sops` encrypts the Secret on its way into the file, with the organisation's key, which the rule
   above picks:

    ```sh
    kubectl create secret generic my-secret \
    --namespace=org-${ORG_NAME} \
    --from-literal=token=CHANGE_ME \
    --dry-run=client \
    -o yaml |
    sops --encrypt --filename-override ${ORG_SECRETS}/secret.enc.yaml /dev/stdin > ${ORG_SECRETS}/secret.enc.yaml
    yq -i '.resources += ["secret.enc.yaml"]' ${ORG_SECRETS}/kustomization.yaml
    ```

1. Push the changes.

`namespace/secrets/kustomization.yaml` gives every Secret there the deletion protection of the keys. Put Secrets that
Flux may delete with their files in another directory of `namespace`, with a rule of their own for the organisation's
key.

## Decrypt a cluster's files

Flux decrypts a file only when the `Kustomization` that applies it says which key to use. A workload cluster's
`Kustomization`s, `WC_NAME.yaml` and `WC_NAME-apps.yaml`, name the cluster's key Secret in `spec.decryption`. Both need
it if both directories have encrypted files: `WC_NAME.yaml` applies `cluster`, and `WC_NAME-apps.yaml` the rest.

```sh
for f in ${WC_NAME}.yaml ${WC_NAME}-apps.yaml; do
  yq -i '.spec.decryption = {"provider": "sops", "secretRef": {"name": "sops-gpg-'"${WC_NAME}"'"}}' \
    management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${f}
done
```

For an age key, name `sops-age-${WC_NAME}` instead. The
[WC_NAME.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME.yaml) example has it.

A `Kustomization` reads the Secret in its own namespace, so the key has to be in the organisation's namespace with
them, in `namespace/secrets`. A `Kustomization` on the management cluster that applies `out-of-band` to the workload
cluster through its kubeconfig, such as the template's `-direct` one, decrypts with a key of its own, such as
`WC_NAME-direct.gpgkey.enc.yaml` in the same directory, made the same way, see
[Add the -direct `Kustomization`](../tutorials/advanced/out-of-band.md#add-the--direct-kustomization).

## Encrypt an app's values

Values you'd rather not keep in plain text go into the app's `-user-secrets` Secret, encrypted with the cluster's key.
The app's `HelmRelease` reads it last, see [App values](../reference/values.md#app-values). The cluster needs a key
first, with the rule for its `apps` directory.

> [!Caution]
> If an `ExternalSecret` already writes the app's `-user-secrets`, don't add a SOPS copy of it: the two would overwrite
> each other. Put the value in your secret manager, or in a Secret of another name, see
> [One Secret, one route](../explanation/secrets.md#one-secret-one-route).

1. In the app's directory, put the Helm values into the `values` key of the Secret, encrypted with the cluster's key,
   which the cluster's rule picks. Keep the `reconcile.fluxcd.io/watch` label, so a change reaches the app at once: CI
   fails without it. A GPG key has to be in your keyring for `sops` to encrypt with it, so import the cluster's public
   key first; an age key needs nothing:

    ```sh
    export APP_NAME=APP_NAME
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
    gpg --import "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc"
    cat <<EOF | sops --encrypt --filename-override secret.enc.yaml /dev/stdin > secret.enc.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-${APP_NAME}-user-secrets
      namespace: org-\${organization}
    stringData:
      values: |
        # secret values of the app for this cluster
    EOF
    ```

    Run it as it is, then put the real values in with `sops edit`, see
    [Change encrypted values](#change-encrypted-values): typed into the command, they'd land in your shell history.

    `sops edit` needs the cluster's private key. Encrypting needs only its public key, imported above for a GPG key, so
    if that's all you have, put the value in as you encrypt instead. `read -rs` reads it without it landing in your
    shell history or on the screen, and the heredoc and the pipe hand it to `sops` on standard input, so it's on no
    command line in the process list either. Replace `KEY` with where the app's values expect it. The single quotes keep
    YAML from reading anything into the value, so type a `'` in it twice:

    ```sh
    read -rs APP_SECRET
    cat <<EOF | sops --encrypt --filename-override secret.enc.yaml /dev/stdin > secret.enc.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-${APP_NAME}-user-secrets
      namespace: org-\${organization}
    stringData:
      values: |
        KEY: '${APP_SECRET}'
    EOF
    unset APP_SECRET
    ```

1. List it, and push. An app with a `kustomization.yaml` of its own lists it there. An app whose files the cluster's
   `apps/kustomization.yaml` lists one by one, such as `WC_NAME/apps/cert-manager`, gets it listed there, as
   `APP_NAME/secret.enc.yaml`:

    ```sh
    if [ -f kustomization.yaml ]; then
      yq -i '.resources += ["secret.enc.yaml"]' kustomization.yaml
    else
      yq -i '.resources += ["'"${APP_NAME}"'/secret.enc.yaml"]' ../kustomization.yaml
    fi
    ```

The Secret names `${cluster_name}` and `${organization}`, which Flux fills in after it decrypts the file, so the
encrypted file stays as it is. To label a Secret that's already encrypted, don't edit the file: add a patch to the
app's `kustomization.yaml`, as the `envoy-gateway-from-template` example of the `WC_NAME_OUT_OF_BAND_FLUX_APP` cluster
does, or edit it with `sops edit`.

## Change encrypted values

To change an encrypted file, you need the private key it was encrypted for.

1. Import the cluster's private key from your password manager, see
   [Keep a private key in a password manager](#keep-a-private-key-in-a-password-manager). For an age key, point
   `sops` at it instead:

    ```sh
    export SOPS_AGE_KEY_FILE=$(pwd)/${WC_NAME}.agekey
    ```

1. Edit the file. `sops edit` decrypts it into your editor and encrypts it again when you save:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
    sops edit secret.enc.yaml
    ```

    To change it with other tools, decrypt it into a temporary file outside the repository, change it there, and
    encrypt it back into place:

    ```sh
    export PLAIN=$(mktemp)
    sops --decrypt secret.enc.yaml > ${PLAIN}
    ```

    Edit the values under `.stringData.values` in `${PLAIN}`. If the Secret holds them base64-encoded under
    `.data.values` instead, as Secrets created with `kubectl create secret` do, decode them into a second temporary
    file, edit that, and encode them back:

    ```sh
    export VALUES=$(mktemp)
    yq .data.values ${PLAIN} | base64 -d > ${VALUES}
    # edit ${VALUES}
    export NEW_USER_VALUES=$(base64 < ${VALUES} | tr -d '\n')
    yq -i ".data.values = \"${NEW_USER_VALUES}\"" ${PLAIN}
    rm ${VALUES}
    ```

    Then encrypt it back, and delete the temporary file:

    ```sh
    sops --encrypt --filename-override secret.enc.yaml ${PLAIN} > secret.enc.yaml
    rm ${PLAIN}
    ```

1. Remove the private key from your keyring, or delete the age key file, and push:

    ```sh
    export KEY_FP=$(gpg --show-keys --with-colons \
    "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc" |
    awk -F: '/^fpr/{print $10; exit}')
    gpg --delete-secret-keys "${KEY_FP}"
    ```

## Keep a private key in a password manager

Flux has its own copy of every private key, in a Secret on the management cluster. You need yours to change the
encrypted files, and to rebuild the Secret if it's lost. Keep it in a password manager, and nowhere else.

For example, with the 1Password CLI, `op`, store a GPG private key as the body of a secure note. The `jq` filter wraps
the armoured key into the item template, in the `notesPlain` field. Replace `YOUR_VAULT` with the vault you keep the
keys in. For the master key or an organisation key, name the item `(${MC_NAME}, master, Flux)` or
`(${MC_NAME}, ${ORG_NAME}, Flux)` instead:

```sh
export VAULT=YOUR_VAULT
export ITEM="GPG private key (${MC_NAME}, ${WC_NAME}, Flux)"
eval $(op signin)
gpg --export-secret-keys --armor "${KEY_FP}" |
jq -Rs '{"fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "label": "notesPlain", "value": .}]}' |
op item create --vault "${VAULT}" --category securenote --title "${ITEM}" --format json -
```

To import the key back into your keyring later, read the note body:

```sh
op item get "${ITEM}" --vault "${VAULT}" --format json |
jq -j '.fields[] | select(.id == "notesPlain") | .value' |
gpg --import
```

An age key is a file, so store the file's contents the same way, and write them back to a file to use it:

```sh
jq -Rs '{"fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES", "label": "notesPlain", "value": .}]}' \
  ${WC_NAME}.agekey |
op item create --vault "${VAULT}" --category securenote --title "age private key (${MC_NAME}, ${WC_NAME}, Flux)" --format json -
op item get "age private key (${MC_NAME}, ${WC_NAME}, Flux)" --vault "${VAULT}" --format json |
jq -j '.fields[] | select(.id == "notesPlain") | .value' > ${WC_NAME}.agekey
```

Other password managers work the same way: store the armoured key or the age key file as a secret note, and read it
back into `gpg --import` or a file.
