# Move an app's chart to an `OCIRepository`

This page moves a `HelmRelease` that takes its chart from a `HelmRepository` or a `GitRepository` to an
`OCIRepository` on `gsoci.azurecr.io`, the way the template's apps take theirs. The release is upgraded in place: it
keeps its name, its history and its objects, and gets one more revision.

A `HelmRelease` with `spec.chart` keeps working, so nothing forces the move. But Giant Swarm publishes its charts to
`gsoci.azurecr.io`, and its old app catalogs on GitHub Pages aren't guaranteed to keep receiving new versions. So
move an app before you next need to upgrade it.

- [What has to stay the same](#what-has-to-stay-the-same)
- [Before you start](#before-you-start)
- [Add the `OCIRepository`](#add-the-ocirepository)
- [Switch the `HelmRelease` to `chartRef`](#switch-the-helmrelease-to-chartref)
- [Remove the old source](#remove-the-old-source)
- [Back out](#back-out)

Export the names the commands use. `HR_NAME` is the `HelmRelease`'s `metadata.name`, and `WC_CONTEXT` is the workload
cluster's context in your kubeconfig, as [the basic tutorial](../tutorials/basic/getting-started.md) sets it up:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export HR_NAME=HELMRELEASE_NAME
export WC_CONTEXT=gs-${MC_NAME}-${WC_NAME}-clientcert
```

## What has to stay the same

helm-controller finds the release it manages by its release name, in its storage namespace. Moving the chart's source
changes neither, unless you change them on the way. Keep these as they are:

| What | Why |
| --- | --- |
| the `HelmRelease`'s `metadata.name` and namespace | A `HelmRelease` with a new name is a new object. Flux prunes the old one, which uninstalls the release, and the new one installs it again |
| `releaseName`, or its absence | Without it, the release name is `TARGET_NAMESPACE-HELMRELEASE_NAME`, or the `HelmRelease`'s name when there's no `targetNamespace`, shortened to 53 characters with a hash. Don't add one that comes out different, and don't drop one that's set |
| `targetNamespace` and `storageNamespace` | Where the release is installed and where Helm keeps its record. Both default to the `HelmRelease`'s namespace |
| the chart's name | The `name` in the chart's `Chart.yaml`, which Helm records with the release |

Change any of the last three on a `HelmRelease` that has installed its release, and helm-controller uninstalls the
release and installs it again under the new identity: the app is down in between, its history starts again at
revision 1 and, unless the chart keeps them, its CRDs go with it, and every resource of those kinds. A new
`HelmRelease` that takes over from something which doesn't uninstall, such as a suspended `HelmRelease` or a paused
`App`, and comes out with a different release name, installs a second release next to the first. It takes over the
objects both name, as [How a `HelmRelease` adopts a release](./adopt-app.md#how-a-helmrelease-adopts-a-release)
describes, and the first release stays `deployed`, with nothing managing it any more.

So this page changes one thing, where the chart comes from, and nothing else. The chart version and the values stay as
they are too: change them in later commits, as [Change an app](./update-app.md) describes.

## Before you start

1. Find the `HelmRelease` and its release:

    ```sh
    kubectl get helmrelease ${HR_NAME} -n org-${ORG_NAME} -o yaml \
      | yq '.spec.chart, .spec.releaseName, .spec.targetNamespace, .spec.storageNamespace,
            (.status.history | sort_by(.version) | .[-1]
              | pick(["name", "namespace", "version", "chartName", "chartVersion"]))'
    export APP_CHART=CHART_NAME
    export APP_VERSION=CHART_VERSION
    export RELEASE_NAME=RELEASE_NAME
    export RELEASE_NAMESPACE=RELEASE_NAMESPACE
    ```

    The last block is the release helm-controller installed last: `APP_CHART` is its `chartName`, `APP_VERSION` its
    `chartVersion`, and `RELEASE_NAME` and `RELEASE_NAMESPACE` its `name` and `namespace`. Take the version from
    there, not from `spec.chart.spec.version`, which may be a range.

    **Check:** the `HelmRelease` is `Ready`. Move a release that's up to date and working: if it isn't, a failure
    afterwards can't be told from the one before.

1. Check that the same chart, at the same version, is on `gsoci.azurecr.io`:

    ```sh
    helm show chart oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART} --version ${APP_VERSION}
    ```

    **Check:** it prints the chart's metadata, with `name: ${APP_CHART}` and `version: ${APP_VERSION}`. A Giant Swarm
    chart has the same name in the old catalogs and on `gsoci.azurecr.io`. If you can't find it under that name, or
    the name in `Chart.yaml` is a different one, stop: a chart with another name reinstalls the release. Ask Giant
    Swarm which chart replaces it.

1. Find the `HelmRelease`'s file in your fork. An app from an
   [App Template](../tutorials/intermediate/app-templates.md) or a [stack](../tutorials/intermediate/stacks.md) has
   it in the base, and changing it there moves the app in every cluster that uses the base. That's fine, as long as
   they all run the same version; if they don't, the version comes from each cluster's patch, as
   [Change an app](./update-app.md) says.

## Add the `OCIRepository`

Add the chart's source first, on its own, so that you can see it's there before the release depends on it. Write
`oci-repository.yaml` beside `helm-release.yaml`, with the same name as the `HelmRelease`, as the template's apps do:

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: OCIRepository
metadata:
  labels:
    giantswarm.io/cluster: ${cluster_name}
  name: HELMRELEASE_NAME
  namespace: org-${organization}
spec:
  interval: 10m
  provider: generic
  ref:
    tag: CHART_VERSION
  url: oci://gsoci.azurecr.io/charts/giantswarm/CHART_NAME
```

`spec.ref.tag` is `APP_VERSION`, exactly. helm-controller refuses a chart whose version isn't the tag it came from,
with `artifact revision ... does not match chart version ...`. Don't use `spec.ref.semver` yet: a range can pick a
newer version than the release runs, and the move then upgrades the app as well. Add the file to the
`kustomization.yaml` of its directory, commit and push.

**Check:** the `OCIRepository` is `Ready`, at `CHART_VERSION@sha256:...`. Nothing reads it yet, so the release
hasn't changed:

```sh
flux get sources oci ${HR_NAME} -n org-${ORG_NAME}
```

## Switch the `HelmRelease` to `chartRef`

1. In `helm-release.yaml`, replace `spec.chart` with `spec.chartRef`, and change nothing else:

    ```yaml
    spec:
      chartRef:
        kind: OCIRepository
        name: HELMRELEASE_NAME
        namespace: org-${organization}
    ```

    `chart` and `chartRef` can't both be set: the API server refuses a `HelmRelease` with both, or neither.

    **Check:** render the cluster's `Kustomization` before and after the change, as
    [Render what Flux applies](./check-changes.md#render-what-flux-applies) shows, and compare the `HelmRelease`.
    The only difference is `chart` gone and `chartRef` in its place. `metadata.name`, `releaseName`,
    `targetNamespace`, `storageNamespace` and `valuesFrom` are the same as before.

1. Commit and push.

    helm-controller deletes the `HelmChart` it generated from `spec.chart`, and loads the chart from the
    `OCIRepository` instead. From an `OCIRepository`, it adds the first 12 characters of the artifact's digest to the
    chart's version, as `APP_VERSION+DIGEST`, so that it notices when a tag is pushed again. Helm recorded the release
    with `APP_VERSION` alone, so helm-controller sees a changed chart and upgrades the release, with the same values.
    That upgrade is the revision you're about to check. The objects change only where the chart writes its own
    version into them, such as a `helm.sh/chart` label.

    **Check:** the `HelmRelease` is `Ready`, and its message says it upgraded the release, one revision on from the
    one you noted:

    ```sh
    flux get helmreleases ${HR_NAME} -n org-${ORG_NAME}
    helm history ${RELEASE_NAME} -n ${RELEASE_NAMESPACE} --kube-context ${WC_CONTEXT} --max 3
    ```

    You see `Helm upgrade succeeded for release RELEASE_NAMESPACE/RELEASE_NAME.vN with chart
    CHART_NAME@CHART_VERSION+DIGEST`, where `N` is one more than the `version` you noted, and `helm history` shows
    that revision as `deployed` and the one before as `superseded`. The `HelmChart` named `org-${ORG_NAME}-${HR_NAME}`,
    in the old source's namespace, is gone.

    **If it says `Helm install succeeded` instead,** the release was installed again: its history starts at revision
    1, or a second release is in `helm list -A`. The identity changed after all; compare the two renders again to see
    which field. For a second release next to the first, follow the steps under "If it says `Helm install succeeded`
    instead" in [Adopt a release installed with Helm](./adopt-app.md#adopt-a-release-installed-with-helm), which make
    Helm forget the old release without deleting its objects.

    **If the upgrade fails,** the message is `Helm upgrade failed for release ...` with Helm's error, and the
    template's `upgrade.remediation` rolls back and retries, see
    [A `HelmRelease` has run out of retries](./troubleshooting.md#a-helmrelease-has-run-out-of-retries). The rollback
    keeps the release's name and history.

From here the version lives in `oci-repository.yaml`, like every other app's. To upgrade it, or to let Flux pick new
versions by itself, see [Change an app](./update-app.md#change-the-chart-version).

## Remove the old source

Once the `HelmRelease` is `Ready` from the `OCIRepository`, the old `HelmRepository` or `GitRepository` may have
nothing left to do. Check that before you take it out of Git: `prune: true` deletes it, and every `HelmRelease` still
reading it then fails with `could not get Source object`.

1. Leave it alone if your fork doesn't define it. A source that isn't in your fork belongs to someone else, such as
   Giant Swarm.
1. Never remove the `GitRepository` that reads your fork. Every `Kustomization` reads it, and an app that took its
   chart from it doesn't change that.
1. Look for anything else that reads it. A `HelmRepository` or `GitRepository` in `default` can serve `HelmRelease`s
   in every organisation, so look in all namespaces, for `HelmRelease`s and for `HelmChart`s:

    ```sh
    export SOURCE_KIND=HelmRepository  # or GitRepository
    export SOURCE_NAME=SOURCE_NAME
    export SOURCE_NAMESPACE=SOURCE_NAMESPACE
    kubectl get helmreleases.helm.toolkit.fluxcd.io -A -o json \
      | jq -r --arg k "${SOURCE_KIND}" --arg n "${SOURCE_NAME}" --arg ns "${SOURCE_NAMESPACE}" '
          .items[] | .spec.chart.spec.sourceRef as $s
          | select($s.kind == $k and $s.name == $n and ($s.namespace // .metadata.namespace) == $ns)
          | "\(.metadata.namespace)/\(.metadata.name)"'
    kubectl get helmcharts.source.toolkit.fluxcd.io -n ${SOURCE_NAMESPACE} -o json \
      | jq -r --arg k "${SOURCE_KIND}" --arg n "${SOURCE_NAME}" '
          .items[] | select(.spec.sourceRef.kind == $k and .spec.sourceRef.name == $n) | .metadata.name'
    grep -rn "${SOURCE_NAME}" management-clusters bases
    ```

    **Check:** the first two print nothing. A `HelmChart` the second one lists is generated by a `HelmRelease` the
    first one missed, or is in Git on its own. `grep` finds what isn't on this management cluster yet, such as a
    `ResourceSet` that renders a `HelmRelease`, or a cluster in another branch.

1. Delete the source's file, and its entry in its `kustomization.yaml`, commit and push.

    **Check:** the source is gone, and every `HelmRelease` is still `Ready`:

    ```sh
    flux get sources all -A
    flux get helmreleases -A --status-selector ready=false
    ```

## Back out

Every step is a commit, so back out by reverting them, newest first. None of them changes the release's identity, so
none reinstalls it.

- **The old source:** revert its removal, and wait for it to be `Ready` before you go on.
- **The switch to `chartRef`:** revert it. helm-controller creates the `HelmChart` again and loads the chart from the
  old source. The chart's version is `APP_VERSION` again, without the digest, so it upgrades the release once more,
  to the next revision. `Helm upgrade succeeded` tells you it did.
- **The `OCIRepository`:** revert it once the `HelmRelease` no longer names it. Before that, the `HelmRelease` fails
  with `could not get Source object`.

Don't roll the release back with `helm rollback` instead. helm-controller sees a revision it didn't make, and upgrades
the release to what Git says at its next reconciliation.
