# Adopt an app that's already installed

This page brings an app that already runs in a workload cluster under this repository, without uninstalling it and
installing it again. It covers a release installed by hand with `helm install`, and a release that a Giant Swarm `App`
custom resource manages through the App Platform, which Giant Swarm is
[deprecating](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/) in favour
of Flux `HelmRelease`s.

One rule runs through every step: at no moment do two things reconcile the release. A `HelmRelease` can take over a
Helm release that's already there. A `HelmRelease` and an `App`, or two `HelmRelease`s, reconciling one release undo
each other's changes for as long as both exist.

- [How a `HelmRelease` adopts a release](#how-a-helmrelease-adopts-a-release)
- [When not to adopt](#when-not-to-adopt)
- [Adopt a release installed with Helm](#adopt-a-release-installed-with-helm)
- [Adopt a release managed by an `App`](#adopt-a-release-managed-by-an-app)
- [Back out](#back-out)

Export the names the commands use. `WC_CONTEXT` is the workload cluster's context in your kubeconfig, as
[the basic tutorial](../tutorials/basic/getting-started.md) sets it up:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export WC_CONTEXT=gs-${MC_NAME}-${WC_NAME}-clientcert
```

## How a `HelmRelease` adopts a release

On every reconciliation, helm-controller looks in the workload cluster for a Helm release with the `HelmRelease`'s
release name, in its storage namespace. A `HelmRelease` that has never installed anything and finds a release there
treats it as not managed by Flux yet, and upgrades it. That upgrade is the adoption: the release keeps its name, its
history and its objects, and gets one more revision.

Four fields decide where helm-controller looks, and the template's app `HelmRelease`s set all four:

| Field | Has to be | Default when it's left out |
| --- | --- | --- |
| `releaseName` | the existing release's name | `TARGET_NAMESPACE-HELMRELEASE_NAME`, which an existing release rarely has |
| `storageNamespace` | the namespace holding the release's `sh.helm.release.v1` Secrets | the `HelmRelease`'s namespace, `org-ORG_NAME` |
| `targetNamespace` | the namespace the release is installed in | the `HelmRelease`'s namespace |
| `kubeConfig.secretRef.name` | `${cluster_name}-kubeconfig`, the workload cluster's | none: the chart goes into the management cluster |

Get `releaseName` or `storageNamespace` wrong and nothing fails. helm-controller finds no release, installs a second
one, and takes ownership of the objects the first one created. You'd then have two Helm releases claiming the same
objects. The `HelmRelease`'s message tells you which happened: `Helm upgrade succeeded` means it adopted the release,
`Helm install succeeded` means it didn't.

The upgrade installs the chart version and the values in Git, nothing else. helm-controller doesn't reuse the values
the release had: a value set with `--set` at install time and missing from Git is gone after the first reconciliation.
So the first commit pins the version that's running and carries the values that are set, and changes nothing. Change
the version or the values in later commits, once the `HelmRelease` is `Ready`, as [Change an app](./update-app.md)
describes.

CRDs in the chart's `crds/` directory follow `install.crds` and `upgrade.crds`. The template's `HelmRelease`s set
neither, so helm-controller uses the defaults: `Create` on install, which creates CRDs that don't exist yet, and `Skip`
on upgrade, which leaves CRDs alone. An adoption is an upgrade, so it doesn't touch the CRDs already in the cluster.
To have later upgrades update them, set `upgrade.crds: CreateReplace` in a commit of its own (see the
[HelmRelease documentation](https://fluxcd.io/flux/components/helm/helmreleases/#upgrade-configuration)). CRDs in
the chart's templates are ordinary objects of the release and are upgraded like the rest.

## When not to adopt

Don't adopt a release that something else already reconciles. Look on the management cluster for a `HelmRelease` that
names it:

```sh
kubectl get helmreleases.helm.toolkit.fluxcd.io -n org-${ORG_NAME} \
  -o custom-columns='NAME:.metadata.name,RELEASE:.spec.releaseName,TARGET:.spec.targetNamespace,CREATED_BY:.metadata.annotations.meta\.helm\.sh/release-name'
```

- A `HelmRelease` with your release's name and target namespace already manages it. If `CREATED_BY` names the
  workload cluster's own release, it's one of the cluster's default apps, which the cluster chart creates. Those are
  Giant Swarm's: configure them in the cluster's values instead (see
  [Configure the default apps](./cluster-values.md#configure-the-default-apps)). A second `HelmRelease` for one would
  fight the cluster chart's for good.
- A `HelmRelease` you wrote yourself, in another directory of this repository, already manages it too. Move that one
  instead (see [Make it a base app](./add-app.md#make-it-a-base-app) for how a move keeps the objects).
- An `App` for it means the App Platform manages it: follow
  [Adopt a release managed by an `App`](#adopt-a-release-managed-by-an-app), not the Helm steps.

## Adopt a release installed with Helm

You need `helm` 3.13 or newer for `helm get metadata`, and the workload cluster's kubeconfig.

1. Find the release in the workload cluster:

    ```sh
    helm list -A --all --kube-context ${WC_CONTEXT}
    export APP_NAME=RELEASE_NAME
    export APP_NAMESPACE=RELEASE_NAMESPACE
    ```

    `APP_NAME` is the release's `NAME`, `APP_NAMESPACE` its `NAMESPACE`. `--all` lists releases in every state, not
    only the deployed and failed ones.

    **Check:** its `STATUS` is `deployed`. Adopt only a deployed release: in any other state, Flux would take over a
    release whose state nobody knows, and a failure afterwards couldn't be told from an old one. A `pending-install`
    or `pending-upgrade` release is a Helm operation cut short or still running. Finish or fix it by hand first.

1. Find where Helm stores the release:

    ```sh
    kubectl --context ${WC_CONTEXT} get secrets -A -l owner=helm,name=${APP_NAME}
    ```

    **Check:** the Secrets, `sh.helm.release.v1.${APP_NAME}.v1` and on, are in `APP_NAMESPACE`. The `helm` command
    stores a release in the namespace it installs into, so they nearly always are. If they're somewhere else, use that
    namespace for `storageNamespace` below instead of `APP_NAMESPACE`.

1. Read the chart and version that run, and the values that were set:

    ```sh
    helm get metadata ${APP_NAME} -n ${APP_NAMESPACE} --kube-context ${WC_CONTEXT}
    helm get values ${APP_NAME} -n ${APP_NAMESPACE} --kube-context ${WC_CONTEXT} -o yaml > /tmp/${APP_NAME}-values.yaml
    export APP_CHART=CHART
    export APP_VERSION=VERSION
    ```

    `APP_CHART` and `APP_VERSION` are the `CHART` and `VERSION` lines. `helm get values` prints only the values
    someone set, not the chart's defaults, which is what you want to carry over.

    Helm doesn't record which repository the chart came from: you have to know. A Giant Swarm chart is at
    `oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART}`.

    **Check:** the version is there to pull. This prints the chart's metadata, with the same `version`:

    ```sh
    helm show chart oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART} --version ${APP_VERSION}
    ```

1. Write the app's files as [Add an app directly](./add-app.md#add-an-app-directly) does, with the names above, and
   stop before you commit. That `HelmRelease` already has `releaseName: ${APP_NAME}`,
   `storageNamespace: ${APP_NAMESPACE}`, `targetNamespace: ${APP_NAMESPACE}` and the cluster's `kubeConfig`. If the
   storage namespace was different in step 2, change `storageNamespace` to it. Then split the values from step 3
   between the layers (see [App values](../reference/values.md#app-values)):

    - the plain values go into `override_config.yaml`, the `-user-values` layer;
    - passwords, tokens and keys go into the `-user-secrets` Secret, never into Git in plain text: through your
      secret manager ([Give an app secret values](./external-secrets.md#give-an-app-secret-values)) or a
      SOPS-encrypted file ([Encrypt an app's values](./sops.md#encrypt-an-apps-values)).

    Delete `/tmp/${APP_NAME}-values.yaml` once you've moved them: it holds the secret values in plain text.

    **Check:** the files render as Flux will apply them (see
    [Check a change before you push](./check-changes.md)).

1. Compare what the `HelmRelease` would install with what runs. The template's app `HelmRelease` reads the cluster's
   values first, `${WC_NAME}-cluster-values`, which a release installed by hand never had. Your values come later and
   win, but a key only the cluster values set is new to the release:

    ```sh
    kubectl get configmap ${WC_NAME}-cluster-values -n org-${ORG_NAME} \
      -o jsonpath='{.data.values}' > /tmp/cluster-values.yaml
    helm get manifest ${APP_NAME} -n ${APP_NAMESPACE} --kube-context ${WC_CONTEXT} > /tmp/before.yaml
    helm template ${APP_NAME} oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART} --version ${APP_VERSION} \
      -n ${APP_NAMESPACE} -f /tmp/cluster-values.yaml -f override_config.yaml -f SECRET_VALUES_FILE > /tmp/after.yaml
    diff /tmp/before.yaml /tmp/after.yaml
    ```

    `SECRET_VALUES_FILE` is a decrypted copy of the secret values; delete it afterwards.

    **Check:** the only differences are ones you expect. `helm template` doesn't talk to the cluster, so anything the
    chart generates at random or reads with `lookup` differs every time; read past those. A real difference, such as
    a changed image, replica count or host name, means a value is missing from your layers or the cluster values
    change it: fix `override_config.yaml` before you commit.

1. Commit and push.

    **Check:** the `HelmRelease` is `Ready`, and its message says it upgraded the release, at one revision more than
    `helm list` showed:

    ```sh
    flux get helmreleases ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
    helm history ${APP_NAME} -n ${APP_NAMESPACE} --kube-context ${WC_CONTEXT} --max 3
    ```

    You see `Helm upgrade succeeded for release APP_NAMESPACE/APP_NAME.vN with chart APP_CHART@APP_VERSION`.

    **If it says `Helm install succeeded` instead,** helm-controller didn't find the release: `releaseName` or
    `storageNamespace` doesn't match, and there are now two releases in the workload cluster, the new one owning the
    objects. `helm list -A` shows both. Suspend the `HelmRelease` at once, and don't delete it while it isn't
    suspended: that uninstalls the new release, and with it the objects both releases share.

    ```sh
    flux suspend helmrelease ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
    ```

    Then make Helm forget the release you installed by hand, without touching what it installed. Helm keeps a
    release as Secrets, one per revision, labelled `owner=helm` and `name=` the release's name. Delete those of the
    old release and nothing else. (`helm uninstall --cascade orphan` is the other way to drop a release. It deletes
    the release's own objects and spares what they own, such as a Deployment's Pods, so something has to create the
    objects again. Deleting the record deletes nothing.)

    ```sh
    helm list -A --kube-context ${WC_CONTEXT}  # the two releases, with their names and namespaces
    kubectl get secret -n OLD_NAMESPACE -l owner=helm,name=OLD_RELEASE_NAME --context ${WC_CONTEXT}
    kubectl delete secret -n OLD_NAMESPACE -l owner=helm,name=OLD_RELEASE_NAME --context ${WC_CONTEXT}
    ```

    `OLD_NAMESPACE` and `OLD_RELEASE_NAME` are those of the release you installed by hand. Where both releases have
    the same name, in two namespaces, the namespace tells them apart; where they're in one namespace, the name does.
    Read what the second command lists before you run the third: it should be the old release's revisions,
    `sh.helm.release.v1.OLD_RELEASE_NAME.v1` and on, and no other.

    **Check:** `helm list -A` shows one release, the one Flux installed, and the app's objects are as they were. Then
    resume the `HelmRelease`:

    ```sh
    flux resume helmrelease ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
    ```

    > **Caution:**
    > This is for two releases that list the same objects, which `helm get manifest` shows for each. If the chart
    > names its objects after the release and the names differed, the new release made a second copy of the app
    > beside the first. Ask Giant Swarm before you remove either one.

    **If the upgrade fails,** the message is `Helm upgrade failed for release ...` with Helm's error, and the
    template's `upgrade.remediation` rolls back and retries, see
    [A `HelmRelease` has run out of retries](./troubleshooting.md#a-helmrelease-has-run-out-of-retries).

    Before you adopt something that matters, try these steps on a copy of it in a test cluster, a failed first
    upgrade included.

From here the app is an ordinary app of the repository. Change it as [Change an app](./update-app.md) says.

## Adopt a release managed by an `App`

An `App` on the management cluster tells app-operator to create a `Chart` in the workload cluster, and chart-operator
installs and upgrades the Helm release the `Chart` describes. Deleting an `App` runs that backwards: app-operator
deletes the `Chart`, and chart-operator uninstalls the release. So the `App` can't simply be swapped for a
`HelmRelease` in one commit. The order is:

1. Pause the `App` and its `Chart`, so that neither operator acts on them any more, deletion included.
1. Let a `HelmRelease` adopt the release, as above.
1. Delete the `Chart` and the `App` without their operators: removing the finalizer first, so nothing uninstalls.

Giant Swarm's migration tool, `appcr-to-helmrelease-converter`, does all three, and checks each step. The steps below
use it as Giant Swarm's
[migration guide](https://docs.giantswarm.io/overview/fleet-management/app-management/app-platform-deprecation/)
describes, and put the result into this repository's layout. It needs [`uv`](https://docs.astral.sh/uv/) and
`kubectl` access to the management cluster:

```sh
alias appcr-to-helmrelease-converter='uvx --from git+https://github.com/giantswarm/appcr-to-helmrelease-converter@main appcr-to-helmrelease-converter'
export APP_CR=APP_CR_NAME
```

This covers an `App` that installs into a workload cluster (`spec.kubeConfig.inCluster: false`). An `App` with
`inCluster: true` installs into the management cluster, which isn't yours to manage: ask Giant Swarm.

### Where each field goes

| `App` | `HelmRelease` and the app's files |
| --- | --- |
| `metadata.name` | `metadata.name` of the `HelmRelease` and of the `OCIRepository`, unchanged |
| the release name, which `helm list` shows | `releaseName`. For an `App` on a workload cluster it's usually the `App`'s name without the cluster name |
| `spec.namespace` | `targetNamespace` and `storageNamespace` |
| `spec.name` | the chart, at the end of the `OCIRepository`'s `url` |
| `spec.catalog` | the start of the `OCIRepository`'s `url`: the `Catalog`'s OCI repository, `oci://gsoci.azurecr.io/charts/giantswarm` for Giant Swarm's catalogue |
| `spec.version` | `spec.ref.tag` of the `OCIRepository` |
| `spec.kubeConfig.secret.name` | `kubeConfig.secretRef.name`; the template's is `${cluster_name}-kubeconfig`, so check the `App` names that Secret |
| `spec.config.configMap` | the first layer; the template's is `${cluster_name}-cluster-values` |
| `spec.userConfig.configMap` | `override_config.yaml`, the `-user-values` layer |
| `spec.userConfig.secret` | the `-user-secrets` Secret |
| `spec.extraConfigs` | more `valuesFrom` entries, in the order of their `priority` |
| annotation `app-operator.giantswarm.io/depends-on` | `spec.dependsOn` |

The `HelmRelease` keeps the `App`'s name on purpose: the migration tool creates its own `HelmRelease` with that name,
and the one in Git has to be the same object, or there would be two. Its cleanup also looks for the `HelmRelease` by
the `App`'s name.

### Steps

1. Read the `App`, and find its release in the workload cluster:

    ```sh
    kubectl get app ${APP_CR} -n org-${ORG_NAME} -o yaml
    helm list -n APP_NAMESPACE --kube-context ${WC_CONTEXT}
    ```

    `APP_NAMESPACE` is the `App`'s `spec.namespace`.

    **Check:** the `App`'s `status.release.status` is `deployed` and its `status.version` is its `spec.version`, and
    the release is `deployed` in `helm list`. The migration tool refuses an `App` that isn't deployed. If the `App`
    has the labels `kustomize.toolkit.fluxcd.io/name` and `kustomize.toolkit.fluxcd.io/namespace`, a Flux
    `Kustomization` applies it, most likely from this repository: find its file now, as you'll take it out later.

1. Let the migration tool write the Flux objects, without changing anything on the cluster:

    ```sh
    appcr-to-helmrelease-converter migrate --name ${APP_CR} --namespace org-${ORG_NAME} \
      --dry-run --output /tmp/${APP_CR}-flux.yaml
    ```

    **Check:** the output has an `OCIRepository` and a `HelmRelease`, both named `${APP_CR}`, and the `HelmRelease`'s
    `releaseName` and `targetNamespace` are the release's name and namespace from `helm list`. If the tool stops
    with a preflight error, it says why; fix that first.

1. Write the app's files in this repository, as [Add an app directly](./add-app.md#add-an-app-directly) does, and stop
   before you commit. Take the names from the tool's output and the table above. If `${cluster_name}-${APP_NAME}`
   doesn't come out as the `App`'s name, set `metadata.name` of the `HelmRelease` and the `OCIRepository`, and the
   `HelmRelease`'s `chartRef.name`, to the `App`'s name. Copy the values of the `App`'s user ConfigMap, under the
   key the tool's `valuesFrom` names, into `override_config.yaml`, and those of its user Secret into the
   `-user-secrets` Secret. Add an entry to `valuesFrom` for each `extraConfigs` source the tool lists.

    The `App`'s `spec.config` needs nothing from you. The App Platform sets it to the cluster's values ConfigMap,
    `${cluster_name}-cluster-values`, when an `App` doesn't name one (see
    [Defaulting and validation of App CRs](https://docs.giantswarm.io/tutorials/fleet-management/app-platform/defaulting-validation/)),
    and that's the template's first layer already. Only if someone set `spec.config` to another ConfigMap by hand,
    add that one to `valuesFrom` as well, after the cluster's values.

    If the `App` and its ConfigMap and Secret are in this repository, take them out in the same change. If the
    ConfigMap or Secret has the name of one of the new layers, replace its file rather than adding a second one:
    kustomize refuses two objects of one name in one build.

    **Check:** the files render (see [Check a change before you push](./check-changes.md)), and the rendered
    `HelmRelease` has the name, `releaseName`, namespaces and `kubeConfig` of the tool's output.

1. Run the migration. It labels the `App` with `kustomize.toolkit.fluxcd.io/reconcile: disabled` if a Flux
   `Kustomization` applies it, so Flux neither changes nor deletes it any more. It annotates the `App` with
   `app-operator.giantswarm.io/paused: "true"` and the `Chart` in the workload cluster with
   `chart-operator.giantswarm.io/paused: "true"`, applies its `OCIRepository` and `HelmRelease`, and waits for the
   `HelmRelease` to be `Ready`:

    ```sh
    appcr-to-helmrelease-converter migrate --name ${APP_CR} --namespace org-${ORG_NAME}
    ```

    The `Chart` is in the `giantswarm` namespace of the workload cluster, so you need to be allowed to change it there.

    **Check:** the tool reports the `HelmRelease` `Ready`, and its message is `Helm upgrade succeeded for release
    ...`, as in step 6 of the Helm steps. If the `HelmRelease` doesn't get there, the tool offers to revert: say yes,
    and it suspends and deletes its `HelmRelease` and `OCIRepository` and takes the annotations and the label off
    again, so the App Platform carries on as before.

1. Commit and push the files from step 3. Flux applies the `HelmRelease` from Git over the one the tool applied: they
   have the same name, so it's one object, now in a `Kustomization`'s inventory. The `App` it leaves alone, because of
   the label.

    **Check:** the `HelmRelease` is `Ready` at the new commit, its `valuesFrom` lists the template's layers, and
    it carries the `kustomize.toolkit.fluxcd.io/name` label:

    ```sh
    flux get helmreleases ${APP_CR} -n org-${ORG_NAME}
    kubectl get helmrelease ${APP_CR} -n org-${ORG_NAME} -o yaml | yq '.metadata.labels, .spec.valuesFrom'
    ```

    If your values come to the same as the `App`'s, Flux finds nothing to change and the release stays at its
    revision. If they don't, Flux upgrades it to what Git says: check the values before you push.

    The tool leaves nothing of note behind on the `HelmRelease`. If you'd like to see for yourself, compare the
    object on the cluster with the file in Git.

1. Delete the `App` and its `Chart`. The tool's `cleanup` checks first that the `HelmRelease` is `Ready`, not
   suspended, applied by a `Kustomization`, and that the `App` has Flux reconciliation disabled. Then it removes the
   finalizers and deletes the `Chart` first and the `App` second:

    ```sh
    appcr-to-helmrelease-converter cleanup --name ${APP_CR} --namespace org-${ORG_NAME} --dry-run
    appcr-to-helmrelease-converter cleanup --name ${APP_CR} --namespace org-${ORG_NAME}
    ```

    It can't read your repository: if the `App` is still in Git, Flux creates it again. Take it out first, in step 3.

    The cleanup is final. After it there's no way back to the App Platform, only forward, so run it once you're
    content with the `HelmRelease`.

    [Something is stuck Terminating](./troubleshooting.md#something-is-stuck-terminating) says not to remove a
    finalizer while its controller can still do its job. Here, the job is to uninstall the release, which is exactly
    what you don't want, so removing it is the point.

    **Check:** the `App` and the `Chart` are gone, and the release is still there, at the same revision:

    ```sh
    kubectl get app ${APP_CR} -n org-${ORG_NAME}
    helm history RELEASE_NAME -n APP_NAMESPACE --kube-context ${WC_CONTEXT} --max 3
    ```

    A paused `App` or `Chart` that's deleted without its finalizer removed doesn't uninstall anything either: its
    operator skips paused objects, deletions included, so it waits `Terminating` until the finalizer goes.

## Back out

**Before anything reaches the cluster,** that is before you push for a release installed with Helm, and before you
run `migrate` without `--dry-run` for an `App`, nothing has changed. Throw the branch away.

**After a release installed with Helm was adopted,** give it back without uninstalling it. Deleting a `HelmRelease`
uninstalls its release, unless the `HelmRelease` is suspended:

1. Set `spec.suspend: true` in the app's `helm-release.yaml`, commit and push.

    **Check:** the `HelmRelease` on the cluster is suspended:

    ```sh
    kubectl get helmrelease ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME} -o jsonpath='{.spec.suspend}'
    ```

1. Only then delete the app's files and take it out of the cluster's `apps/kustomization.yaml`, commit and push.

    **Check:** the `HelmRelease` is gone and the release is still `deployed` in `helm list`.

The release stays at the revision Flux gave it. To go back to the revision installed by hand, roll it back with
`helm rollback ${APP_NAME} REVISION -n ${APP_NAMESPACE} --kube-context ${WC_CONTEXT}`, with `REVISION` from
`helm history`.

**After an `App` was migrated, before the cleanup,** the `App` and the `Chart` still exist, paused, and the App
Platform takes the release back, also after Flux has upgraded it. The steps are the migration tool's own revert, in
its order:

1. Suspend the `HelmRelease`: in Git as above once you've pushed its files, or before that with
   `flux suspend helmrelease ${APP_CR} -n org-${ORG_NAME}`. Check it's suspended.
1. Delete it: take its files out of Git and push, or before you've pushed them, delete the objects the tool applied
   with `kubectl delete helmrelease,ocirepository ${APP_CR} -n org-${ORG_NAME}`. Put the `App` and its ConfigMap and
   Secret back in Git if they were there, and push.
1. Take the annotations off the `Chart` and the `App`, and the label off the `App`:

    ```sh
    appcr-to-helmrelease-converter resume --name ${APP_CR} --namespace org-${ORG_NAME}
    kubectl label app ${APP_CR} -n org-${ORG_NAME} kustomize.toolkit.fluxcd.io/reconcile-
    ```

    **Check:** the `App`'s `status.release.status` is `deployed` again.

**After the cleanup,** the `App` and the `Chart` are gone.

> [!Caution]
> There's no way back to the App Platform from here. Keep the `HelmRelease`, and fix forward.
