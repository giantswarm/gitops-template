# Multicluster apps

An organisation in this repository is usually a department, with many clusters. Some apps belong on all of them, or
on most: a logging agent, a policy set, a team's service. Listing the app in every cluster's `apps` works, but it's
one more directory to add, and keep in step, for every cluster you create.

A multicluster app is written once, in `${ORG_DIR}/multicluster/apps`, as a Flux Operator `ResourceSet`. The
organisation lists its clusters once, in `${ORG_DIR}/multicluster/apps/clusters.yaml`, and every app in the directory
is installed on every cluster in that list. Adding a cluster to the list rolls all of them out to it.

This tutorial sets up `${ORG_DIR}/multicluster/apps` in the organisation from the
[basic tutorial](../basic/getting-started.md), lists its clusters, and adds hello-world as a multicluster app, upgraded
only in an upgrade window. It builds on [Scheduled upgrades](./scheduled-upgrades.md), which explains the
`ResourceSetInputProvider` and the `ResourceSet`. It creates no cluster: the app goes on the clusters you already
have.

> [!Caution]
> A cluster that already has an app in its own `apps` mustn't get it from a `ResourceSet` too: two `HelmRelease`s for
> one release keep upgrading over each other. Take the app out of the cluster's `apps` before you list the cluster
> here. See [One owner per object](../../explanation/one-owner.md#two-helmreleases-for-one-release).

- [The multicluster directory](#the-multicluster-directory)
- [List the clusters](#list-the-clusters)
- [Add an app](#add-an-app)
- [Upgrade production later](#upgrade-production-later)
- [Clusters that aren't ready yet](#clusters-that-arent-ready-yet)
- [Next steps](#next-steps)

The fork has the finished example in the example organisation:
[multicluster/apps](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/apps/). The steps write the
same files, without their comments. Run the commands from the root of your clone, with the variables the basic
tutorial exported still set: those from [Before you start](../basic/getting-started.md#before-you-start), and the ones
its steps add.

## The multicluster directory

The management cluster's Flux `Kustomization` doesn't apply `${ORG_DIR}/multicluster/apps` itself. It applies another
`Kustomization`, in `${ORG_DIR}/multicluster/apps.yaml`, and that one applies `${ORG_DIR}/multicluster/apps`, with
`${organization}` filled in. The apps then have a `Kustomization` of their own: a mistake in one of them doesn't stop
the management cluster's.

1. Create the directory, and its `kustomization.yaml`, which lists only `apps.yaml`. The organisation's
   `multicluster` directory may already hold `secret-stores`, if you gave every cluster a store with
   [Kyverno](../../how-to/workload-cluster-secrets.md#give-every-cluster-a-store-with-kyverno). Leave it out of this
   list: the organisation's namespace `Kustomization` applies it, into the organisation's namespace:

    ```sh
    mkdir -p ${ORG_DIR}/multicluster/apps
    cat <<'EOF' > ${ORG_DIR}/multicluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    kind: Kustomization
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
    resources:
      - apps.yaml
    EOF
    ```

1. Create the `Kustomization` that applies `${ORG_DIR}/multicluster/apps`. It lives in `default`, as the management
   cluster's `Kustomization` applies it, and runs as the `automation` ServiceAccount there. Like `namespace.yaml`, it
   depends on the management cluster's `Kustomization`, which applies every commit first, and has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation: if Flux deleted it, it would take every `ResourceSet` in
   the directory with it, and their apps from every cluster. `ORG_NAME` is a placeholder that the organisation's
   `kustomization.yaml` replaces with the `Organization`'s name, as it does for `namespace.yaml`:

    ```sh
    cat <<EOF > ${ORG_DIR}/multicluster/apps.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      annotations:
        kustomize.toolkit.fluxcd.io/prune: disabled
      name: ${MC_NAME}-multicluster-apps-${ORG_NAME}
      namespace: default
    spec:
      dependsOn:
        - name: ${MC_NAME}-gitops
      interval: 10m
      path: "./${ORG_DIR}/multicluster/apps"
      postBuild:
        substitute:
          organization: "ORG_NAME"
      prune: true
      retryInterval: 1m
      serviceAccountName: automation
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
      timeout: 2m
    EOF
    ```

1. List `multicluster` in the organisation's `kustomization.yaml`:

    ```sh
    yq -i '.resources += ["multicluster"] | .resources |= unique' ${ORG_DIR}/kustomization.yaml
    ```

## List the clusters

`${ORG_DIR}/multicluster/apps/clusters.yaml` names the clusters, by their `cluster_name`.
`${ORG_DIR}/multicluster/apps/kustomization.yaml` applies it as a patch to every `ResourceSet` in the directory, which
sets their `spec.inputs`:

1. Export the clusters, separated by spaces: the cluster from the basic tutorial, and any others in the organisation:

    ```sh
    export MULTICLUSTER_CLUSTERS="${WC_NAME}"
    ```

1. Create the list. The `ResourceSet`'s name in it is a placeholder: kustomize puts the name of each `ResourceSet` it
   patches there:

    ```sh
    cat <<'EOF' > ${ORG_DIR}/multicluster/apps/clusters.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSet
    metadata:
      name: every-resource-set
    spec:
      inputs: []
    EOF
    for c in $(echo "${MULTICLUSTER_CLUSTERS}"); do
      yq -i '.spec.inputs += [{"cluster": "'"${c}"'"}]' ${ORG_DIR}/multicluster/apps/clusters.yaml
    done
    ```

1. Create `${ORG_DIR}/multicluster/apps/kustomization.yaml`, which applies the list to every `ResourceSet` and, for
   now, lists no app:

    ```sh
    cat <<'EOF' > ${ORG_DIR}/multicluster/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    kind: Kustomization
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
    patches:
      - path: clusters.yaml
        target:
          kind: ResourceSet
    resources: []
    EOF
    ```

To roll every app out to another cluster later, add its name to `clusters.yaml`. That's enough only when the cluster
has what each app depends on, see [Clusters that aren't ready yet](#clusters-that-arent-ready-yet). Removing a name
uninstalls the apps from that cluster. To give one app a list of its own, add a patch after `clusters.yaml` in
`kustomization.yaml` that targets that `ResourceSet` by name and sets its `spec.inputs`.

Removing the last name is the exception: it uninstalls nothing. With no clusters, a `ResourceSet` has no
`inputs.hello_world_scheduled` to render with, so its build fails with `map has no entry for key`, and it keeps what it
installed. That's the safe way to fail, but it isn't what you meant. To take an app off every cluster, remove it from
`kustomization.yaml`: Flux deletes its `ResourceSet`, which uninstalls it everywhere. An empty
`MULTICLUSTER_CLUSTERS` in the step above gives you the empty list, too.

## Add an app

An app is a directory with a `ResourceSetInputProvider` and a `ResourceSet`, one `ResourceSet` per app, as in
[Scheduled upgrades](./scheduled-upgrades.md#schedule-an-apps-upgrades). The difference is `inputStrategy: Permute`:
the `ResourceSet` combines every cluster in its `spec.inputs` with the version its provider exports, and renders an
`OCIRepository` and a `HelmRelease` for each cluster. With `Permute`, the inputs of each source are under the source's
name, with `_` for `-`: the `ResourceSet`'s own inputs, from `clusters.yaml`, under `inputs.hello_world_scheduled`, and
the provider's under `inputs.hello_world_scheduled_version`.

1. Create the provider. It picks the highest hello-world release below `4.0.0`, from Monday to Thursday, 09:00 to 17:00
   in Berlin:

    ```sh
    mkdir -p ${ORG_DIR}/multicluster/apps/hello-world-scheduled
    cat <<'EOF' > ${ORG_DIR}/multicluster/apps/hello-world-scheduled/input-provider.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    metadata:
      name: hello-world-scheduled-version
      namespace: org-${organization}
    spec:
      type: OCIArtifactTag
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
      filter:
        semver: '>=3.2.2 <4.0.0'
        limit: 1
      schedule:
        - cron: "0 9 * * 1-4"
          timeZone: Europe/Berlin
          window: 8h
    EOF
    ```

1. Create the `ResourceSet`. Each cluster's objects are named after the cluster, so they don't collide in the
   organisation's namespace, and each `HelmRelease` uses its cluster's kubeconfig Secret and cluster values:

    ```sh
    cat <<'EOF' > ${ORG_DIR}/multicluster/apps/hello-world-scheduled/resource-set.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSet
    metadata:
      name: hello-world-scheduled
      namespace: org-${organization}
    spec:
      dependsOn:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: hello-world-scheduled-version
          namespace: org-${organization}
          ready: true
          readyExpr: >-
            status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
            && has(status.exportedInputs)
      inputStrategy:
        name: Permute
      inputsFrom:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: hello-world-scheduled-version
      serviceAccountName: automation
      resources:
        - apiVersion: source.toolkit.fluxcd.io/v1
          kind: OCIRepository
          metadata:
            labels:
              giantswarm.io/cluster: << inputs.hello_world_scheduled.cluster >>
            name: << inputs.hello_world_scheduled.cluster >>-hello-world-scheduled
            namespace: << inputs.hello_world_scheduled_version.provider.namespace >>
          spec:
            interval: 10m
            provider: generic
            ref:
              tag: << inputs.hello_world_scheduled_version.tag | quote >>
            url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
        - apiVersion: helm.toolkit.fluxcd.io/v2
          kind: HelmRelease
          metadata:
            labels:
              giantswarm.io/cluster: << inputs.hello_world_scheduled.cluster >>
            name: << inputs.hello_world_scheduled.cluster >>-hello-world-scheduled
            namespace: << inputs.hello_world_scheduled_version.provider.namespace >>
          spec:
            chartRef:
              kind: OCIRepository
              name: << inputs.hello_world_scheduled.cluster >>-hello-world-scheduled
            dependsOn:
              - name: << inputs.hello_world_scheduled.cluster >>-gateway-api-crds
            install:
              createNamespace: true
              remediation:
                remediateLastFailure: false
                retries: 10
            interval: 5m
            kubeConfig:
              secretRef:
                name: << inputs.hello_world_scheduled.cluster >>-kubeconfig
            releaseName: hello-world-scheduled
            storageNamespace: hello-world-scheduled
            targetNamespace: hello-world-scheduled
            timeout: 10m
            upgrade:
              remediation:
                remediateLastFailure: true
                retries: 10
                strategy: rollback
            values:
              ingress:
                enabled: false
              route:
                enabled: true
                parentRefs:
                  - name: giantswarm-default
                    namespace: envoy-gateway-system
                hostnames:
                  - "hello-scheduled.{{ .Values.baseDomain }}"
            valuesFrom:
              - kind: ConfigMap
                name: << inputs.hello_world_scheduled.cluster >>-cluster-values
                valuesKey: values
    EOF
    ```

    hello-world gets an `HTTPRoute` at `hello-scheduled.<base domain>` on each cluster's `giantswarm-default`
    Gateway. `{{ .Values.baseDomain }}` is Helm's, not the `ResourceSet`'s, whose placeholders are `<< >>`. Each
    listed cluster's Gateway has to list `hello-scheduled` in `listeners.https.subdomains`, or the hostname gets no DNS
    record and no certificate: the out-of-band example clusters list it in
    `cluster/apps/envoy-gateway-from-template/user_config_gateway_api_config.yaml`.

    A `ResourceSet` deletes what it rendered for an input that has gone, which is how removing a cluster from
    `clusters.yaml` uninstalls the app there. It's also why every app has a `ResourceSet` of its own: apps that shared
    one would go together.

1. List the app in `${ORG_DIR}/multicluster/apps/kustomization.yaml`, then commit and push:

    ```sh
    yq -i '.resources += ["hello-world-scheduled/input-provider.yaml", "hello-world-scheduled/resource-set.yaml"]' \
      ${ORG_DIR}/multicluster/apps/kustomization.yaml
    git add ${ORG_DIR} && git commit -m "Install hello-world on the clusters of ${ORG_NAME}" && git push
    ```

**Check:** the multicluster `Kustomization` is `Ready`, and the `ResourceSet` has rendered a `HelmRelease` per cluster.
Until the provider's first window nothing is rendered: force `hello-world-scheduled-version` once, as
[Install before the first window](./scheduled-upgrades.md#install-before-the-first-window) shows, to install at once.

```sh
flux get kustomizations ${MC_NAME}-multicluster-apps-${ORG_NAME} -n default
kubectl get resourceset hello-world-scheduled -n org-${ORG_NAME}
flux get helmreleases -n org-${ORG_NAME} | grep hello-world-scheduled
```

If it doesn't get there, see [When something isn't Ready](../../how-to/troubleshooting.md).

If you followed [Scheduled upgrades](./scheduled-upgrades.md) on the same cluster, it keeps its `hello-world-window`
from there. That one has names, a release and a namespace of its own, so the two `ResourceSet`s never render the same
object, and neither deletes what the other installed.

## Upgrade production later

Every cluster in the list upgrades in the same window. The provider exports one version, `Permute` pairs it with every
cluster, and when the window opens on a new version, Flux Operator applies the new tag to all of them in one go: dev and
production in the same minute. Rollback remediation catches an upgrade that fails, not one that succeeds and then
misbehaves. For a logging agent that may be fine. For anything production would notice, give production a window of
its own.

Production then gets its own provider, with a later window, and its own list of clusters, which means a second app made
from the first: a `ResourceSet` reads one provider here, and `Permute` would pair every provider with every cluster.

1. Export the production clusters, and the directory of the apps:

    ```sh
    export PROD_CLUSTERS="CLUSTER_NAME"
    export APPS_DIR=${ORG_DIR}/multicluster/apps
    ```

1. Copy the `ResourceSet` as `hello-world-scheduled-prod`. With `Permute`, its inputs follow its name and its
   provider's, so the keys change with them, `inputs.hello_world_scheduled_prod` and
   `inputs.hello_world_scheduled_prod_version`. The objects get names of their own, so the two `ResourceSet`s never
   render the same one; the Helm release keeps its name and namespace on every cluster:

    ```sh
    mkdir -p ${APPS_DIR}/hello-world-scheduled-prod
    sed -e 's/hello-world-scheduled/hello-world-scheduled-prod/g' -e 's/hello_world_scheduled/hello_world_scheduled_prod/g' \
      -e 's/releaseName: hello-world-scheduled-prod/releaseName: hello-world-scheduled/' \
      -e 's/storageNamespace: hello-world-scheduled-prod/storageNamespace: hello-world-scheduled/' \
      -e 's/targetNamespace: hello-world-scheduled-prod/targetNamespace: hello-world-scheduled/' \
      ${APPS_DIR}/hello-world-scheduled/resource-set.yaml > ${APPS_DIR}/hello-world-scheduled-prod/resource-set.yaml
    ```

1. Create its provider, the same range on Fridays, and its list of clusters. Each production cluster leaves
   `clusters.yaml`: a cluster is in one list, never both. Then list the files, and the patch that sets the production
   `ResourceSet`'s clusters, after `clusters.yaml`:

    ```sh
    yq '.metadata.name = "hello-world-scheduled-prod-version" | .spec.schedule[0].cron = "0 9 * * 5"' \
      ${APPS_DIR}/hello-world-scheduled/input-provider.yaml > ${APPS_DIR}/hello-world-scheduled-prod/input-provider.yaml
    cat <<'EOF' > ${APPS_DIR}/hello-world-scheduled-prod/clusters.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSet
    metadata:
      name: hello-world-scheduled-prod
    spec:
      inputs: []
    EOF
    for c in ${PROD_CLUSTERS}; do
      yq -i '.spec.inputs += [{"cluster": "'"${c}"'"}]' ${APPS_DIR}/hello-world-scheduled-prod/clusters.yaml
      yq -i 'del(.spec.inputs[] | select(.cluster == "'"${c}"'"))' ${APPS_DIR}/clusters.yaml
    done
    yq -i '.resources += ["hello-world-scheduled-prod/input-provider.yaml", "hello-world-scheduled-prod/resource-set.yaml"] |
      .patches += [{"path": "hello-world-scheduled-prod/clusters.yaml", "target": {"kind": "ResourceSet", "name": "hello-world-scheduled-prod"}}]' \
      ${APPS_DIR}/kustomization.yaml
    ```

    If other apps here need the production clusters too, keep them in `clusters.yaml`, and give `hello-world-scheduled`
    a list of its own the same way.

1. Before you push, suspend each production cluster's `HelmRelease`. Taking a cluster out of `clusters.yaml` deletes
   its `HelmRelease`, and deleting one that isn't suspended uninstalls hello-world there. A suspended one is deleted
   without uninstalling anything, and the production `HelmRelease` then
   [adopts the release](../../how-to/adopt-app.md#how-a-helmrelease-adopts-a-release) it finds, since it has the same
   release name and namespaces. Suspend them on the management cluster, not in Git: one template renders every
   cluster's `HelmRelease`, so a patch to it would suspend dev too. The `ResourceSet` doesn't set `spec.suspend`, so
   it leaves the suspension alone:

    ```sh
    for c in ${PROD_CLUSTERS}; do
      flux suspend helmrelease ${c}-hello-world-scheduled -n org-${ORG_NAME}
    done
    ```

    **Check:** each one is suspended:

    ```sh
    kubectl get helmrelease -n org-${ORG_NAME} -o custom-columns='NAME:.metadata.name,SUSPENDED:.spec.suspend' | grep hello-world-scheduled
    ```

1. Commit and push, and force the new provider once, as for any new provider.

    **Check:** the suspended `HelmRelease`s are gone, and each production cluster's
    `CLUSTER_NAME-hello-world-scheduled-prod` says `Helm upgrade succeeded`. Until the provider is forced, hello-world
    keeps running there with nothing managing it. If one says `Helm install succeeded` instead, it didn't find the
    release: see that check in
    [Adopt a release installed with Helm](../../how-to/adopt-app.md#adopt-a-release-installed-with-helm).

Windows space upgrades out in time; they don't promote. A version published on a Thursday evening, after the others'
window has closed, reaches production on Friday, before anyone else has run it. If production must only get what the
others have run, pin its range to that version, as the stages pin a release in
[Promote a change from dev to prod](../intermediate/stages-and-regions.md#promote-a-change-from-dev-to-prod), and move
the pin on when you're happy.

## Clusters that aren't ready yet

A listed cluster may not exist yet, or not be ready. The example app doesn't install early: hello-world has the
cluster's `gateway-api-crds` release in `dependsOn`, which only gets ready once the cluster is up, and helm-controller
retries until then. That dependency is the example app's own, and needs envoy-gateway on that cluster, from the
[hello-web](../intermediate/stacks.md) stack, for example. On a cluster without it, hello-world stays
`DependencyNotReady`, while the `Kustomization` and the `ResourceSet` report `Ready`.

Nothing fails meanwhile. The `ResourceSet` applies the `HelmRelease` without waiting for it, and the multicluster
`Kustomization` applies only the `ResourceSet` and its provider. Unlike a cluster's apps `Kustomization`, it doesn't
wait for the Cluster API `Cluster`'s control plane. A `HelmRelease` can only depend on other `HelmRelease`s, so an
app of your own without such a dependency would only wait for the cluster's kubeconfig Secret: it fails, and retries,
until the Secret exists. That's harmless, but noisy; give your app a `dependsOn` on a release the cluster installs with
itself if you'd rather it waited quietly.

## Next steps

- [Scheduled upgrades](./scheduled-upgrades.md): the window, and how the `ResourceSet` keeps its version.
- [Limits of kustomize](../../explanation/composition.md#limits-of-kustomize): when a `ResourceSet` fits better than a
  stack.
- [Testing](./testing.md): how the kind test checks the multicluster example.
