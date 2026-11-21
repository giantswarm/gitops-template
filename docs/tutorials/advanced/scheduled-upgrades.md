# Scheduled upgrades

[Automatic updates](../intermediate/automatic-updates.md) install a new version as soon as it's published, at three in
the afternoon or three in the morning, whichever comes first. For a dev cluster that's fine. For the release of a
production cluster, which replaces its nodes, or an app whose users notice when it restarts, you want new versions to
wait for an upgrade window.

Flux Operator, which runs on every Giant Swarm management cluster, does that with two objects of its API,
`fluxcd.controlplane.io/v1`, used as they are:

- a `ResourceSetInputProvider` of type `OCIArtifactTag` lists the tags of a chart, keeps the ones in its
  `spec.filter.semver` range and exports the highest. Its `spec.schedule` decides when it looks.
- a `ResourceSet` renders the app's `OCIRepository` and `HelmRelease` from that version, with `<< inputs.tag >>` where
  the version goes.

This tutorial schedules the upgrades of an app on the cluster from the [basic tutorial](../basic/getting-started.md),
then creates a cluster whose Giant Swarm release moves only in a window.

- [When to use it](#when-to-use-it)
- [Schedule an app's upgrades](#schedule-an-apps-upgrades)
- [Schedule a cluster's release](#schedule-a-clusters-release)
- [Install before the first window](#install-before-the-first-window)
- [How the window works](#how-the-window-works)
- [Keep the version](#keep-the-version)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## When to use it

A plain `HelmRelease` is enough when:

- a pinned version is fine: every upgrade is a pull request, and it reaches the cluster when it's merged;
- a range is fine: the app may upgrade whenever a new version is published.

Use a `ResourceSetInputProvider` and a `ResourceSet` when upgrades have to wait for a window: the release of a
production cluster, or an app that should only restart in working hours. A `ResourceSet` can also roll the same app out
to several clusters from one list, see [Multicluster apps](./multicluster-apps.md).

## Schedule an app's upgrades

The app is a second copy of hello-world, `hello-world-scheduled`, in its own namespace, which upgrades only from Monday
to Thursday, 09:00 to 17:00 in Berlin. It waits for the Gateway API CRDs of the cluster's envoy-gateway, so it needs
the [hello-web](../intermediate/stacks.md) stack, or envoy-gateway, on the cluster.

1. Create the app's directory:

    ```sh
    export APP_DIR=${WC_DIR}/apps/hello-world-scheduled
    mkdir -p ${APP_DIR}
    ```

1. Create the provider. It picks the highest hello-world release below `4.0.0`, and looks only inside the window:

    ```sh
    cat <<'EOF' > ${APP_DIR}/input-provider.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    metadata:
      name: ${cluster_name}-hello-world-scheduled-version
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

    Keep `spec.filter.limit: 1`, or every exported tag becomes a release of its own.

1. Create the `ResourceSet`. It renders the app's `OCIRepository` and `HelmRelease` at the version the provider
   exports. The cluster's apps `Kustomization` fills in `${cluster_name}` and `${organization}` when it applies the
   file, and Flux Operator fills in `<< inputs.* >>` when it renders the objects:

    ```sh
    cat <<'EOF' > ${APP_DIR}/resource-set.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSet
    metadata:
      name: ${cluster_name}-hello-world-scheduled
      namespace: org-${organization}
    spec:
      dependsOn:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: ${cluster_name}-hello-world-scheduled-version
          namespace: org-${organization}
          ready: true
          readyExpr: >-
            status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
            && has(status.exportedInputs)
      inputsFrom:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: ${cluster_name}-hello-world-scheduled-version
      serviceAccountName: automation
      resources:
        - apiVersion: source.toolkit.fluxcd.io/v1
          kind: OCIRepository
          metadata:
            labels:
              giantswarm.io/cluster: ${cluster_name}
            name: ${cluster_name}-hello-world-scheduled
            namespace: << inputs.provider.namespace >>
          spec:
            interval: 10m
            provider: generic
            ref:
              tag: << inputs.tag | quote >>
            url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
        - apiVersion: helm.toolkit.fluxcd.io/v2
          kind: HelmRelease
          metadata:
            labels:
              giantswarm.io/cluster: ${cluster_name}
            name: ${cluster_name}-hello-world-scheduled
            namespace: << inputs.provider.namespace >>
          spec:
            chartRef:
              kind: OCIRepository
              name: ${cluster_name}-hello-world-scheduled
            dependsOn:
              - name: ${cluster_name}-gateway-api-crds
            install:
              createNamespace: true
              remediation:
                remediateLastFailure: false
                retries: 10
            interval: 5m
            kubeConfig:
              secretRef:
                name: ${cluster_name}-kubeconfig
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
                name: ${cluster_name}-cluster-values
                valuesKey: values
    EOF
    ```

    A few things matter here:

    - The `dependsOn` on the provider keeps the app installed if the version ever goes, see
      [Keep the version](#keep-the-version).
    - `serviceAccountName` is the organisation's `automation` ServiceAccount. Flux Operator applies what the
      `ResourceSet` renders with that account's rights, and a Kyverno policy on Giant Swarm management clusters
      rejects a `ResourceSet` without one.
    - The `ResourceSet` and its provider have to be in the same namespace. The rendered objects name theirs
      explicitly, the provider's, with `<< inputs.provider.namespace >>`. The `HelmRelease`'s `chartRef` needs none:
      Flux looks for the `OCIRepository` in the `HelmRelease`'s namespace.
    - Keep one `ResourceSet` per app. A `ResourceSet` deletes what it rendered for an input that has gone, so apps
      that shared one would go together.

1. List the two files in the cluster's apps, then commit and push:

    ```sh
    yq -i '.resources += ["hello-world-scheduled/input-provider.yaml", "hello-world-scheduled/resource-set.yaml"]' \
      ${WC_DIR}/apps/kustomization.yaml
    git add ${WC_DIR}/apps && git commit -m "Schedule hello-world upgrades on ${WC_NAME}" && git push
    ```

**Check:** the provider is `Ready`. Outside the window it exports no version yet, so the app isn't installed until the
window opens, or until you [force the provider once](#install-before-the-first-window). To see which version a
provider picked, and when it looks next:

```sh
kubectl get resourcesetinputproviders -n org-${ORG_NAME} \
  -o 'custom-columns=NAME:.metadata.name,VERSION:.status.exportedInputs[0].tag,NEXT:.status.nextSchedule.when'
```

## Schedule a cluster's release

A cluster's release works the same way, with the cluster's `OCIRepository` and `HelmRelease` in the `ResourceSet`. The
fork's example is
[WC_NAME_SCHEDULED_UPGRADES](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/cluster/cluster-resource-set.yaml),
whose release moves to the highest `v36` release only on Tuesdays, 02:00 to 05:00 UTC. The steps write the same
files, without their comments, for a new cluster in your organisation. To move a cluster that already runs onto this
layout without changing it, see [Move a running cluster to scheduled upgrades](../../how-to/scheduled-upgrades-existing-cluster.md)
instead.

The cluster is still built from the [CAPA cluster base](/bases/clusters/capa) and a region, which give it its values.
Its `ResourceSet` renders the `OCIRepository` and the `HelmRelease` as the base has them, at the version its provider
picks, and a patch drops the base's two.

1. Export the cluster's name, at most 20 characters, and its directory:

    ```sh
    export SU_NAME=CLUSTER_NAME
    export SU_DIR=${ORG_DIR}/workload-clusters/${SU_NAME}
    mkdir -p ${SU_DIR}/cluster
    ```

1. Create the provider. Set the range to the major release you want the cluster on; an exact version, such as one
   release, pins the cluster to it:

    ```sh
    cat <<'EOF' > ${SU_DIR}/cluster/release-input-provider.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    metadata:
      labels:
        giantswarm.io/cluster: ${cluster_name}
      name: ${cluster_name}-release
      namespace: org-${organization}
    spec:
      type: OCIArtifactTag
      url: oci://gsoci.azurecr.io/charts/giantswarm/release-aws
      filter:
        semver: '>=36.0.0 <37.0.0'
        limit: 1
      schedule:
        - cron: "0 2 * * 2"
          timeZone: UTC
          window: 3h
    EOF
    ```

    A new major release is a change to the range in Git. Like a new release, a change to the range reaches the cluster
    at the next window, or at once when you force the provider.

1. Create the `ResourceSet`. Both objects carry the `fluxcd.controlplane.io/prune: disabled` annotation and the
   `giantswarm.io/prevent-deletion` label, as the base's do. The `HelmRelease` lists the region's values itself,
   after the base's, because a Component's patch doesn't reach into a `ResourceSet`:

    ```sh
    cat <<'EOF' > ${SU_DIR}/cluster/cluster-resource-set.yaml
    apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSet
    metadata:
      labels:
        giantswarm.io/cluster: ${cluster_name}
      name: ${cluster_name}
      namespace: org-${organization}
    spec:
      dependsOn:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: ${cluster_name}-release
          namespace: org-${organization}
          ready: true
          readyExpr: >-
            status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
            && has(status.exportedInputs)
      inputsFrom:
        - apiVersion: fluxcd.controlplane.io/v1
          kind: ResourceSetInputProvider
          name: ${cluster_name}-release
      serviceAccountName: automation
      resources:
        - apiVersion: source.toolkit.fluxcd.io/v1
          kind: OCIRepository
          metadata:
            annotations:
              fluxcd.controlplane.io/prune: disabled
            labels:
              giantswarm.io/cluster: ${cluster_name}
              giantswarm.io/managed-by: flux
              giantswarm.io/prevent-deletion: "true"
            name: ${cluster_name}
            namespace: << inputs.provider.namespace >>
          spec:
            interval: 10m0s
            provider: generic
            ref:
              tag: << inputs.tag | quote >>
            timeout: 1m0s
            url: oci://gsoci.azurecr.io/charts/giantswarm/release-aws
        - apiVersion: helm.toolkit.fluxcd.io/v2
          kind: HelmRelease
          metadata:
            annotations:
              fluxcd.controlplane.io/prune: disabled
            labels:
              giantswarm.io/cluster: ${cluster_name}
              giantswarm.io/managed-by: flux
              giantswarm.io/prevent-deletion: "true"
            name: ${cluster_name}
            namespace: << inputs.provider.namespace >>
          spec:
            chartRef:
              kind: OCIRepository
              name: ${cluster_name}
            install:
              remediation:
                remediateLastFailure: false
            interval: 5m0s
            releaseName: ${cluster_name}
            serviceAccountName: automation
            storageNamespace: org-${organization}
            targetNamespace: org-${organization}
            timeout: 10m0s
            upgrade:
              remediation:
                remediateLastFailure: true
                retries: 10
                strategy: rollback
            valuesFrom:
              - kind: ConfigMap
                name: cluster-app-installation-values
                valuesKey: values.yaml
              - kind: ConfigMap
                name: ${cluster_name}-config
                valuesKey: values
              - kind: ConfigMap
                name: ${cluster_name}-region-config
                valuesKey: values
    EOF
    ```

1. Create the patch that drops the base's `OCIRepository` and `HelmRelease`, and the cluster's `kustomization.yaml`:

    ```sh
    cat <<'EOF' > ${SU_DIR}/cluster/patch_delete_base_cluster.yaml
    $patch: delete
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}
      namespace: org-${organization}
    ---
    $patch: delete
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      name: ${cluster_name}
      namespace: org-${organization}
    EOF
    cat <<'EOF' > ${SU_DIR}/cluster/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    components:
      - ../../../../../../../bases/environments/regions/eu_central
    kind: Kustomization
    labels:
      - pairs:
          giantswarm.io/managed-by: flux
    patches:
      - path: patch_delete_base_cluster.yaml
    resources:
      - ../../../../../../../bases/clusters/capa
      - release-input-provider.yaml
      - cluster-resource-set.yaml
    EOF
    cat <<'EOF' > ${SU_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - cluster/
    EOF
    ```

1. Create the cluster's `Kustomization`. It sets no `release`: the provider picks it:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${SU_NAME}.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${SU_NAME}
    spec:
      dependsOn:
        - name: ${MC_NAME}-organization-${ORG_NAME}
          namespace: default
      interval: 10m
      path: "./${SU_DIR}"
      postBuild:
        substitute:
          cluster_description: "description"
          cluster_name: "${SU_NAME}"
          organization: "\${organization}"
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

1. List it in the organisation's clusters, then commit and push:

    ```sh
    yq -i '.resources += ["'"${SU_NAME}"'.yaml"]' ${ORG_DIR}/workload-clusters/kustomization.yaml
    git add ${ORG_DIR}/workload-clusters && git commit -m "Add ${SU_NAME} with scheduled release upgrades" && git push
    ```

The cluster isn't created until its provider exports a release, at the next Tuesday window. To create it now, force
the provider once, below.

## Install before the first window

A new provider whose window is closed reports `Ready`, but exports no version until the window opens. Until then its
`ResourceSet` waits, so the app isn't installed and the cluster isn't created. To install at once, force the provider
once, after Flux has applied it. It then reads the registry outside its schedule, this one time:

```sh
# the app
flux-operator reconcile inputprovider ${WC_NAME}-hello-world-scheduled-version -n org-${ORG_NAME} --force
# the cluster: its provider is named after it
flux-operator reconcile inputprovider ${SU_NAME}-release -n org-${ORG_NAME} --force
```

Without the `flux-operator` CLI, set both annotations to the same new value:

```sh
now="$(date +%s)"
kubectl annotate resourcesetinputprovider ${SU_NAME}-release -n org-${ORG_NAME} --overwrite \
  reconcile.fluxcd.io/requestedAt="${now}" reconcile.fluxcd.io/forceAt="${now}"
```

Later upgrades still wait for the window. The comments in the fork's examples give the same step, and the kind test
does the same for both of them.

## How the window works

With a `window`, the provider looks at the registry only while the window is open: from the `cron` time, in its
`timeZone`, for the length of the window, less the provider's timeout of two minutes. Inside the window it looks every
10 minutes. Outside it, nothing moves the version: not a new release, and not a change to the range in Git either.
Both wait for the next window. A window has to be at least twice the timeout, so at least `4m`.

`window` defaults to `0s`, which Flux Operator's API documents as "no window is applied". That doesn't turn the
schedule off, and it doesn't hold upgrades back either: the provider looks at the `cron` time, and also whenever
something asks it to, such as a change to its spec or a restart of Flux Operator. It only stops looking every 10
minutes. Set a `window` to keep upgrades in the window.

The kind test checks this behaviour, in `tests/ats/resource_set_schedule.py`.

## Keep the version

Without a version, a `ResourceSet` renders nothing and deletes what it rendered before, which uninstalls the app or
deletes the cluster. That's the one way this setup can really hurt. The version goes when no tag matches the range,
when the registry can't be read, or when the provider is deleted. Both `ResourceSet`s above guard against it with the
`dependsOn` on their provider:

```yaml
dependsOn:
  - apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    name: ${cluster_name}-release
    namespace: org-${organization}
    ready: true
    readyExpr: >-
      status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
      && has(status.exportedInputs)
```

Until the provider is `Ready` with a version, the `ResourceSet` reports `DependencyNotReady` and leaves what it rendered
as it is. The cluster's `OCIRepository` and `HelmRelease` also have the `fluxcd.controlplane.io/prune: disabled`
annotation, so the `ResourceSet` never deletes them, not even when the `ResourceSet` itself is deleted or its file is
deleted from Git, and the `giantswarm.io/prevent-deletion` label, as in the cluster base. Keep both whenever you write
a `ResourceSet` that renders a cluster. [Deletion protection](../../explanation/deletion-protection.md#resourcesets)
explains how they work together.

The kind test takes the version away in each of the three ways and checks that the app stays installed, in
`tests/ats/resource_set_guard.py`, and that the cluster's `HelmRelease` and `OCIRepository` stay, also when the
`ResourceSet` is deleted, in `tests/ats/resource_set_cluster_guard.py`.

## Next steps

- [Multicluster apps](./multicluster-apps.md): one `ResourceSet` that installs an app on many clusters.
- [Move a running cluster to scheduled upgrades](../../how-to/scheduled-upgrades-existing-cluster.md).
- [Stages and regions](../intermediate/stages-and-regions.md): a cluster's release pinned per stage instead.
