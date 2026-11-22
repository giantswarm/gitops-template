# Multicluster apps

An organisation in this repository is usually a department, with many clusters. Some apps belong on all of them, or
on most: a logging agent, a policy set, a team's service. Listing the app in every cluster's `apps` works, and it's
one more directory to add, and keep in step, for every cluster you create.

A multicluster app is written once, in `${ORG_DIR}/multicluster/apps`, as a Flux Operator `ResourceSet`. The
organisation lists its clusters once, in `${ORG_DIR}/multicluster/apps/clusters.yaml`, and every app in the directory
is installed on every cluster in that list. Adding a cluster to the list rolls all of them out to it.

This tutorial sets up `${ORG_DIR}/multicluster/apps` in the organisation from the
[basic tutorial](../basic/getting-started.md), lists its clusters, and adds hello-world as a multicluster app, upgraded
only in an upgrade window. It builds on [Scheduled upgrades](./scheduled-upgrades.md), which explains the
`ResourceSetInputProvider` and the `ResourceSet`.

- [The multicluster directory](#the-multicluster-directory)
- [List the clusters](#list-the-clusters)
- [Add an app](#add-an-app)
- [Clusters that aren't ready yet](#clusters-that-arent-ready-yet)
- [Next steps](#next-steps)

The fork has the finished example in the example organisation:
[multicluster/apps](/management-clusters/MC_NAME/organizations/ORG_NAME/multicluster/apps/). The steps write the
same files, without their comments. Run the commands from the root of your clone, with the variables the basic
tutorial exported still set: those from [Before you start](../basic/getting-started.md#before-you-start), and the ones
its steps add.

## The multicluster directory

The management cluster's `Kustomization` doesn't apply `${ORG_DIR}/multicluster/apps` itself. It applies one Flux
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
   cluster's `Kustomization` applies it, and runs as the `automation` ServiceAccount there. `ORG_NAME` is a
   placeholder that the organisation's `kustomization.yaml` replaces with the `Organization`'s name, as it does for
   `namespace.yaml`:

    ```sh
    cat <<EOF > ${ORG_DIR}/multicluster/apps.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-multicluster-apps-${ORG_NAME}
      namespace: default
    spec:
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
    for c in ${MULTICLUSTER_CLUSTERS}; do
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
        semver: '>=3.0.0 <4.0.0'
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
            valuesFrom:
              - kind: ConfigMap
                name: << inputs.hello_world_scheduled.cluster >>-cluster-values
                valuesKey: values
    EOF
    ```

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
Until the provider's first window, there's no version yet and nothing is rendered; to install at once, force the
provider once, as in [Install before the first window](./scheduled-upgrades.md#install-before-the-first-window):

```sh
flux get kustomizations ${MC_NAME}-multicluster-apps-${ORG_NAME} -n default
flux-operator reconcile inputprovider hello-world-scheduled-version -n org-${ORG_NAME} --force
kubectl get resourceset hello-world-scheduled -n org-${ORG_NAME}
flux get helmreleases -n org-${ORG_NAME} | grep hello-world-scheduled
```

If you followed [Scheduled upgrades](./scheduled-upgrades.md) on the same cluster, it keeps its `hello-world-window`
from there. That one has names, a release and a namespace of its own, so the two `ResourceSet`s never render the same
object, and neither deletes what the other installed.

## Clusters that aren't ready yet

A listed cluster may not exist yet, or not be ready. The example app doesn't install early: hello-world has the
cluster's `gateway-api-crds` release in `dependsOn`, which only gets ready once the cluster is up, and helm-controller
retries until then. That dependency is the example app's own, and needs envoy-gateway on that cluster, from the
[hello-web](../intermediate/stacks.md) stack, for example. On a cluster without it, hello-world stays
`DependencyNotReady`, while the `Kustomization` and the `ResourceSet` report `Ready`.

Nothing fails meanwhile. The `ResourceSet` applies the `HelmRelease` without waiting for it, and the multicluster
`Kustomization` applies only the `ResourceSet` and its provider. Unlike a cluster's apps `Kustomization`, it doesn't
wait for the Cluster API `Cluster` to be `Available`. A `HelmRelease` can only depend on other `HelmRelease`s, so an
app of your own without such a dependency would only wait for the cluster's kubeconfig Secret: it fails, and retries,
until the Secret exists. That's harmless, but noisy; give your app a `dependsOn` on a release the cluster installs with
itself if you'd rather it waited quietly.

## Next steps

- [Scheduled upgrades](./scheduled-upgrades.md): the window, and how the `ResourceSet` keeps its version.
- [Limits of kustomize](../../explanation/composition.md#limits-of-kustomize): when a `ResourceSet` fits better than a
  stack.
- [Testing](./testing.md): how the kind test checks the multicluster example.
