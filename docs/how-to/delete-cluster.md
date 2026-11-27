# Delete a workload cluster

This page deletes a workload cluster your fork manages, with its apps, keys and files.

Deleting a cluster's files doesn't delete the cluster, on purpose. Flux deletes the cluster's Flux `Kustomization`s, its
apps and its configuration, but keeps the cluster's `HelmRelease` and `OCIRepository`, because they carry the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation. They also carry the `giantswarm.io/prevent-deletion` label,
so nobody can delete them until the label is removed, and the cluster's `Cluster` has the label too.
[Deletion protection](../explanation/deletion-protection.md) explains why.

So deleting a cluster takes a few deliberate steps, in this order: remove the protection, take the cluster out of the
organisation's multicluster apps, remove what the cluster applies to the workload cluster directly, remove its keys and
its files, and only then delete the cluster by hand.
The [basic tutorial](../tutorials/basic/getting-started.md#6-delete-the-cluster-optional) deletes the cluster it
created the same way.

## Before you start

Export the names the commands use, and run them from the root of your clone. `WC_NAME` is the cluster's name, which
is also the name of its directory and files:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export ORG_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}
export WC_DIR=${ORG_DIR}/workload-clusters/${WC_NAME}
```

Check what you're about to delete:

- **The protection is there.** The steps below rely on it to keep the cluster until the last step, and `kubectl gs`
  doesn't write all of it (see
  [What kubectl-gs writes](../explanation/deletion-protection.md#what-kubectl-gs-writes)). A cluster whose base a
  kubectl-gs older than 8.0.0 wrote may lack the annotation, and one older than 7.0.0 the label. Without the annotation
  on the `OCIRepository`, Flux deletes it with the files, and the `HelmRelease` it keeps loses its chart. Without either
  on the `HelmRelease`, Flux deletes the cluster with them. Check both:

    ```sh
    kubectl get helmrelease,ocirepository ${WC_NAME} -n org-${ORG_NAME} \
      -o custom-columns='KIND:.kind,PRUNE:.metadata.annotations.kustomize\.toolkit\.fluxcd\.io/prune,PREVENT-DELETION:.metadata.labels.giantswarm\.io/prevent-deletion'
    ```

    Both have to print `disabled` and `true`. If they don't, add them to the base and push before you go on.
- **Application teams are gone.** If an application team delivers to the cluster with Flux on the management cluster,
  remove the team from the cluster first, as [Remove a team](../tutorials/advanced/teams.md#remove-a-team) describes.
- **A cluster from a `ResourceSet`**, as in the scheduled-upgrades example, has `fluxcd.controlplane.io/prune:
  disabled` instead of Flux's annotation, and its `ResourceSet` renders it. Its `HelmRelease` and `OCIRepository` stay
  when the `ResourceSet` goes. The steps are the same, except that the patches that remove the protection have to
  target the `ResourceSet`, as the next section shows.

## Remove the deletion protection

Remove the label from the cluster's `OCIRepository` and `HelmRelease`, and set `global.metadata.preventDeletion` to
`false`, so that the chart removes it from the cluster's `Cluster` too. Leave the annotation: it keeps Flux from
deleting them with the files later.

1. Add the patches to the cluster's `kustomization.yaml`:

    ```sh
    yq -i '.patches += [{"patch": "[{\"op\": \"remove\", \"path\": \"/metadata/labels/giantswarm.io~1prevent-deletion\"}]", "target": {"labelSelector": "giantswarm.io/prevent-deletion"}}, {"patch": "{\"apiVersion\": \"helm.toolkit.fluxcd.io/v2\", \"kind\": \"HelmRelease\", \"metadata\": {\"name\": \"cluster\"}, \"spec\": {\"values\": {\"global\": {\"metadata\": {\"preventDeletion\": false}}}}}", "target": {"kind": "HelmRelease", "name": "\\${cluster_name}"}}]' ${WC_DIR}/cluster/kustomization.yaml
    ```

    `spec.values` takes precedence over the ConfigMaps in `valuesFrom`, so this works whatever values the cluster has.
    The second patch targets only the cluster's `HelmRelease`, named `${cluster_name}`, not the base apps in
    `cluster/apps`. kustomize reads the target name as a regular expression, hence the escaped `$`.

    For a cluster a `ResourceSet` renders, those two patches match nothing, and kustomize says nothing about a patch
    that matches nothing: the `HelmRelease` and the `OCIRepository` are entries in the `ResourceSet`'s `resources`,
    not objects kustomize sees. Patch the `ResourceSet` instead, the way its `patch_cluster_userconfig.yaml` does. The
    `OCIRepository` is the first resource and the `HelmRelease` the second, and a `test` before each change fails the
    build if that isn't so. The `HelmRelease` in the example has no `spec.values`, so the patch adds them. If yours
    has some, add `global.metadata.preventDeletion` under them instead of replacing them:

    ```sh
    cat <<'EOF' > ${WC_DIR}/cluster/patch_remove_protection.yaml
    - op: test
      path: /spec/resources/0/kind
      value: OCIRepository
    - op: remove
      path: /spec/resources/0/metadata/labels/giantswarm.io~1prevent-deletion
    - op: test
      path: /spec/resources/1/kind
      value: HelmRelease
    - op: remove
      path: /spec/resources/1/metadata/labels/giantswarm.io~1prevent-deletion
    - op: add
      path: /spec/resources/1/spec/values
      value:
        global:
          metadata:
            preventDeletion: false
    EOF
    yq -i '.patches += [{"path": "patch_remove_protection.yaml", "target": {"group": "fluxcd.controlplane.io", "kind": "ResourceSet", "name": "\\${cluster_name}"}}]' ${WC_DIR}/cluster/kustomization.yaml
    ```

    Check that the patch took, before you push: neither rendered object may carry the label any more, so this has to
    print `OCIRepository: null` and `HelmRelease: null`:

    ```sh
    kubectl kustomize ${WC_DIR}/cluster |
      yq 'select(.kind == "ResourceSet") | .spec.resources[] | .kind + ": " + (.metadata.labels."giantswarm.io/prevent-deletion" // "null")'
    ```

1. Commit and push, and make Flux read the change right away:

    ```sh
    git commit -am "Remove the deletion protection of workload cluster ${WC_NAME}" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    ```

    For a cluster a `ResourceSet` renders, Flux applies the changed `ResourceSet`. As long as its provider is `Ready`
    with a version, Flux Operator applies what it renders at once, without waiting for the upgrade window. Its
    server-side apply takes the label off the live `HelmRelease` and `OCIRepository`, because Flux Operator is the only
    field manager that set it there. A label someone added by hand with `kubectl label` stays; remove that by hand.
    Check the live objects too. The `PREVENT-DELETION` column has to be empty:

    ```sh
    kubectl get helmrelease,ocirepository ${WC_NAME} -n org-${ORG_NAME} -L giantswarm.io/prevent-deletion
    ```

1. Wait until the `Cluster` has lost the label, which takes an upgrade of the chart. The `PREVENT-DELETION` column has
   to be empty:

    ```sh
    kubectl get clusters.cluster.x-k8s.io ${WC_NAME} -n org-${ORG_NAME} -L giantswarm.io/prevent-deletion
    ```

## Take the cluster out of multicluster apps

Skip this section if the cluster isn't in `${ORG_DIR}/multicluster/apps/clusters.yaml`, or in a list of its own that a
patch in `${ORG_DIR}/multicluster/apps/kustomization.yaml` gives one app (see
[Multicluster apps](../tutorials/advanced/multicluster-apps.md)). The organisation's `ResourceSet`s install those apps
on every listed cluster, and the cluster's own files don't know about them. If you leave the cluster in the list, they
keep rendering a `HelmRelease` for a cluster that's gone, and it fails for good.

1. Take the cluster out of the list, then commit and push:

    ```sh
    yq -i 'del(.spec.inputs[] | select(.cluster == strenv(WC_NAME)))' ${ORG_DIR}/multicluster/apps/clusters.yaml
    git commit -am "Take workload cluster ${WC_NAME} out of the multicluster apps" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-multicluster-apps-${ORG_NAME} -n default
    ```

    Do the same in any list of its own. If the cluster is the last one in a list, the `ResourceSet` can't build
    without it and uninstalls nothing: remove that app from `kustomization.yaml` instead.

1. Wait until the `ResourceSet`s have uninstalled the apps from the cluster:

    ```sh
    until [ -z "$(kubectl get helmrelease -n org-${ORG_NAME} \
        -l "resourceset.fluxcd.controlplane.io/name,giantswarm.io/cluster=${WC_NAME}" \
        --field-selector metadata.name!=${WC_NAME} -o name)" ]; do sleep 10; done
    ```

## Remove out-of-band resources

Out-of-band resources reach a workload cluster in one of two ways (see
[Apply resources straight to a workload cluster](../tutorials/advanced/out-of-band.md)):

- Flux in the workload cluster pulls them itself. They go with the cluster, and there's nothing to remove on the
  management cluster for them. Skip this section.
- A `Kustomization` on the management cluster applies them through the cluster's kubeconfig Secret. In the template
  that's `WC_NAME-direct.yaml`, which the steps below call `${ORG_DIR}/workload-clusters/${WC_NAME}-direct.yaml`. If
  you named yours differently, use its name. Skip this section if the cluster has none.

That `Kustomization` has to be gone before you delete the cluster. It reaches the cluster through the cluster's
kubeconfig Secret, which goes with the cluster. Once the Secret is gone, Flux can't reach the cluster any more, and the
`Kustomization` stays `Terminating` for good.

1. Save the name of the key it decrypts with, if any, for the next section. Then take it out of the organisation's
   list of clusters, and remove its file:

    ```sh
    export DIRECT_KEY=$(yq '.spec.decryption.secretRef.name // ""' ${ORG_DIR}/workload-clusters/${WC_NAME}-direct.yaml)
    yq -i 'del(.resources[] | select(. == "'"${WC_NAME}"'-direct.yaml"))' ${ORG_DIR}/workload-clusters/kustomization.yaml
    git rm -q ${ORG_DIR}/workload-clusters/${WC_NAME}-direct.yaml
    ```

1. Commit and push, and make Flux read the change right away:

    ```sh
    git commit -am "Remove the out-of-band resources of workload cluster ${WC_NAME}" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-organization-${ORG_NAME} -n default
    ```

1. Flux deletes the `-direct` `Kustomization`, which deletes the out-of-band resources from the workload cluster.
   Wait until it's gone:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME}-direct -n org-${ORG_NAME} --timeout=10m
    ```

## Remove the cluster's keys

Skip this section if the cluster has no SOPS key. Its `Kustomization`s name the key Secrets they decrypt with in
`spec.decryption`, and the Secrets are in the organisation's `namespace/secrets` (see
[SOPS keys](../reference/sops-keys.md#workload-cluster-keys)). Each key also has a public key in `.sops.keys` and a
rule in `.sops.yaml`. Remove all three from Git now, in the same commit as the cluster's files in the next section.
The Secrets themselves stay on the management cluster, protected, until you delete them in the last section.

1. Save the names of the key Secrets the cluster's `Kustomization`s decrypt with, and the `-direct` one's from the
   section above:

    ```sh
    unset KEYS
    for f in ${WC_NAME}.yaml ${WC_NAME}-apps.yaml; do
      [ -f ${ORG_DIR}/workload-clusters/${f} ] || continue
      KEYS="${KEYS} $(yq '.spec.decryption.secretRef.name // ""' ${ORG_DIR}/workload-clusters/${f})"
    done
    export KEYS=$(echo ${KEYS} ${DIRECT_KEY} | tr ' ' '\n' | sort -u | tr '\n' ' ')
    echo "${KEYS}"
    ```

1. Another cluster's `Kustomization`s may share a key. Check whether one does:

    ```sh
    yq ea 'select(.spec.decryption.secretRef.name as $n | strenv(KEYS) | split(" ") | any_c(. == $n)) |
      select(filename | test("/'"${WC_NAME}"'(-apps|-direct)?\.yaml$") | not) |
      filename + ": " + .spec.decryption.secretRef.name' ${ORG_DIR}/workload-clusters/*.yaml
    ```

    If this prints a file, that cluster uses the key it names: keep the key, and take its name out of `KEYS`.

1. Remove each key's Secret from `namespace/secrets` and its list, and its public key from `.sops.keys`. The public key
   is named after the Secret's file: `.sops.X.asc` for `X.gpgkey.enc.yaml`, and `.sops.X.agekey.pub` for
   `X.agekey.enc.yaml`:

    ```sh
    for key in $(echo ${KEYS}); do
      export KEY_FILE=$(basename "$(KEY=${key} yq ea 'select(.metadata.name == strenv(KEY)) | filename' ${ORG_DIR}/namespace/secrets/*.enc.yaml)")
      yq -i 'del(.resources[] | select(. == strenv(KEY_FILE)))' ${ORG_DIR}/namespace/secrets/kustomization.yaml
      git rm -q ${ORG_DIR}/namespace/secrets/${KEY_FILE}
      case "${KEY_FILE}" in
        *.gpgkey.enc.yaml) PUBLIC_KEY=.sops.${KEY_FILE%.gpgkey.enc.yaml}.asc ;;
        *.agekey.enc.yaml) PUBLIC_KEY=.sops.${KEY_FILE%.agekey.enc.yaml}.agekey.pub ;;
      esac
      git rm -q --ignore-unmatch management-clusters/${MC_NAME}/.sops.keys/${PUBLIC_KEY}
    done
    ```

1. A cluster can have more keys than its first, each with a public key of its own, such as the
   `.sops.${WC_NAME}-APP_NAME.asc` that [Add another key to a cluster](./sops.md#add-another-key-to-a-cluster)
   shares. Their rules point into the cluster's directory, so remove the public key of every key those rules name,
   unless a rule of another cluster still uses it. `gpg --show-keys` only reads each file; it imports nothing:

    ```sh
    export CLUSTER_RULES='.creation_rules[] | select(.path_regex | test("/workload-clusters/'"${WC_NAME}"'/"))'
    export OTHER_RULES='.creation_rules[] | select(.path_regex | test("/workload-clusters/'"${WC_NAME}"'/") | not)'
    for k in $(yq "${CLUSTER_RULES} | (.pgp // \"\"), (.age // \"\")" .sops.yaml | tr -d ' ' | tr ',' '\n' | sort -u); do
      yq "${OTHER_RULES} | (.pgp // \"\"), (.age // \"\")" .sops.yaml | tr -d ' ' | tr ',' '\n' | grep -qixF "${k}" && continue
      for f in management-clusters/${MC_NAME}/.sops.keys/.sops.*; do
        if grep -qxF "${k}" "${f}" ||
          gpg --show-keys --with-colons "${f}" 2>/dev/null | awk -F: '/^fpr/{print $10}' | grep -qixF "${k}"; then
          git rm -q "${f}"
        fi
      done
    done
    ```

1. Remove the cluster's rules from `.sops.yaml`, the ones whose `path_regex` points into the cluster's directory:

    ```sh
    yq -i "del(${CLUSTER_RULES})" .sops.yaml
    ```

1. Delete the private keys from your password manager once the cluster is gone, or keep them if you want to read the
   cluster's encrypted files in the Git history later.

Don't commit yet: the next section commits the keys together with the cluster's files.

## Remove the cluster's files

1. Take the cluster's `Kustomization`s out of the organisation's list of clusters, and remove their files and the
   cluster's directory:

    ```sh
    for f in ${WC_NAME}.yaml ${WC_NAME}-apps.yaml; do
      [ -f ${ORG_DIR}/workload-clusters/${f} ] || continue
      yq -i 'del(.resources[] | select(. == "'"${f}"'"))' ${ORG_DIR}/workload-clusters/kustomization.yaml
      git rm -q ${ORG_DIR}/workload-clusters/${f}
    done
    git rm -rq ${WC_DIR}
    ```

1. If the organisation sends [commit statuses](./commit-statuses.md), take the cluster's `Kustomization`s, the
   `-direct` one included, out of the `eventSources` of its `Alert`:

    ```sh
    export ALERT=${ORG_DIR}/namespace/notifications/commit-status-alert.yaml
    [ -f ${ALERT} ] && yq -i 'del(.spec.eventSources[] |
      select(.name | test("^'"${MC_NAME}-clusters-${WC_NAME}"'(-apps|-direct)?$")))' ${ALERT}
    ```

1. If your [kind test](../reference/ci-checks.md#the-kind-test) knows the cluster, take it out of
   `EXPECTED_NODE_POOLS` in `tests/ats/node_pools.py`, out of `GATES` in `tests/ats/cluster_gates.py`, and remove its
   assertions under `tests/ats/assertions`.

1. Commit and push everything in one go, and make Flux read the change right away:

    ```sh
    git commit -am "Delete workload cluster ${WC_NAME}" && git push
    flux reconcile kustomization ${MC_NAME}-gitops -n default --with-source
    flux reconcile kustomization ${MC_NAME}-organization-${ORG_NAME} -n default
    ```

1. Flux deletes the cluster's `Kustomization`s, which delete the cluster's apps and configuration. Wait until they're
   gone. They're in the organisation's namespace:

    ```sh
    kubectl wait --for=delete kustomization/${MC_NAME}-clusters-${WC_NAME} \
      kustomization/${MC_NAME}-clusters-${WC_NAME}-apps -n org-${ORG_NAME} --timeout=10m
    ```

1. Wait for the cluster's apps to be uninstalled: Flux doesn't. Their `HelmRelease`s go once helm-controller has
   uninstalled them from the workload cluster. The uninstall is what removes what the apps created outside the
   cluster, such as load balancers, volumes and DNS records, and deleting the cluster may leave those behind. Once the
   cluster's kubeconfig Secret has gone, helm-controller skips the uninstall rather than wait for it:

    ```sh
    until [ -z "$(kubectl get helmrelease -n org-${ORG_NAME} \
        -l 'kustomize.toolkit.fluxcd.io/name in ('"${MC_NAME}-clusters-${WC_NAME},${MC_NAME}-clusters-${WC_NAME}-apps"'),kustomize.toolkit.fluxcd.io/namespace=org-'"${ORG_NAME}" \
        --field-selector metadata.name!=${WC_NAME} -o name)" ]; do sleep 10; done
    ```

The cluster's `HelmRelease` and `OCIRepository` are still there, and so is the cluster.

## Delete the cluster

1. If `KEYS` isn't empty, delete the key Secrets now. Flux keeps them on the management cluster, as it does every
   SOPS key Secret. Remove their label first:

    ```sh
    for key in $(echo ${KEYS}); do
      kubectl label secret ${key} -n org-${ORG_NAME} giantswarm.io/prevent-deletion-
      kubectl delete secret ${key} -n org-${ORG_NAME}
    done
    ```

1. Delete the cluster's `HelmRelease`, which no longer has the label. This deletes the cluster and its cloud
   infrastructure. Then delete its `OCIRepository`:

    ```sh
    kubectl delete helmrelease ${WC_NAME} -n org-${ORG_NAME}
    kubectl delete ocirepository ${WC_NAME} -n org-${ORG_NAME}
    ```

**Check:** Cluster API deletes the cluster, which takes a few minutes. Once it's gone, nothing of it is left:

```sh
kubectl gs get clusters -n org-${ORG_NAME}
```

If it doesn't get there, see [When something isn't Ready](./troubleshooting.md#something-is-stuck-terminating).
