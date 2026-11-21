# Out-of-band resources

Everything you've built so far lives on the management cluster. A cluster is a `HelmRelease` there, an app is an
`OCIRepository` and a `HelmRelease` there, and the workload cluster only ever sees what those charts install. That
covers most things, but not all. Sometimes you want a plain object inside the workload cluster: a namespace and a
`RoleBinding` for a team, a ConfigMap an app reads, a policy. Wrapping each of those in a chart of its own is a lot of
packaging for a two-line object.

Those go into the cluster's `out-of-band` directory, and get applied straight to the workload cluster by a third Flux
`Kustomization` on the management cluster, the cluster's `-direct` one. This tutorial adds both to the cluster from the
[basic tutorial](../basic/getting-started.md), then installs Flux in the workload cluster as well, for the Flux objects
that `out-of-band` can deliver there.

- [When to apply directly](#when-to-apply-directly)
- [Add the out-of-band directory](#add-the-out-of-band-directory)
- [Add the -direct Kustomization](#add-the--direct-kustomization)
- [Run Flux in the workload cluster](#run-flux-in-the-workload-cluster)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## When to apply directly

Reach for `out-of-band` when the object belongs in the workload cluster and no chart installs it: namespaces,
`RoleBinding`s, ConfigMaps and Secrets that workloads read, policies, or the `GitRepository` and `Kustomization` of a
[team](./teams.md) whose Flux runs in the workload cluster. When a chart exists for the thing, prefer an app: Helm
tracks its objects and its version, and the cluster's apps wait for the cluster to be ready.

Everything in `cluster` and `apps` is applied to the management cluster. `out-of-band` never is: the cluster
directory's `kustomization.yaml` lists `cluster/` or `apps/`, never `out-of-band/`, so the cluster's `Kustomization`s
leave it out. The cluster's `-direct` `Kustomization` applies it to the workload cluster instead, through the cluster's
kubeconfig Secret, as in the
[out-of-band-no-flux](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/)
example. The `-direct` `Kustomization` is the only thing that applies `out-of-band`. If the workload cluster runs Flux
too, don't point a `Kustomization` of that Flux at the same directory: two Flux installations would fight over the same
objects.

## Add the out-of-band directory

1. Create the directory, with a ConfigMap to show it works:

    ```sh
    mkdir -p ${WC_DIR}/out-of-band/configmaps
    cat <<'EOF' > ${WC_DIR}/out-of-band/configmaps/configmap.yaml
    apiVersion: v1
    data:
      values: |-
        I am the ${cluster_name} cluster, and I belong to the ${organization} organisation.
    kind: ConfigMap
    metadata:
      name: hello-from-out-of-band
      namespace: default
    EOF
    ```

    `${cluster_name}` and `${organization}` are filled in by the `-direct` `Kustomization`, below, the same way as in
    the cluster's other files. Each object names the namespace in the workload cluster it goes into.

1. Check that `${WC_DIR}/kustomization.yaml` doesn't list `out-of-band/`. It must never be applied to the management
   cluster:

    ```sh
    yq '.resources' ${WC_DIR}/kustomization.yaml
    ```

The directory needs no `kustomization.yaml`: Flux applies every YAML file in it, and in the directories below it. Add
one if you want to list the files, or patch them.

## Add the -direct Kustomization

The `-direct` `Kustomization` applies `out-of-band` with the cluster's kubeconfig Secret, `${WC_NAME}-kubeconfig`,
which the management cluster creates in `org-${ORG_NAME}` once the cluster is up. A `Kustomization` reads its
kubeconfig Secret from its own namespace, so it goes in the organisation's `workload-clusters`, next to the cluster's
other two: the organisation's namespace `Kustomization` applies it into `org-${ORG_NAME}`.

1. Create it. It names no namespace, reads your `GitRepository` in `default`, and depends on the organisation's
   namespace `Kustomization`, like the cluster's. `\${organization}` keeps the variable in the file for the
   organisation's namespace `Kustomization` to fill in:

    ```sh
    cat <<EOF > ${ORG_DIR}/workload-clusters/${WC_NAME}-direct.yaml
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ${MC_NAME}-clusters-${WC_NAME}-direct
    spec:
      dependsOn:
        - name: ${MC_NAME}-organization-${ORG_NAME}
          namespace: default
      interval: 10m
      kubeConfig:
        secretRef:
          name: ${WC_NAME}-kubeconfig
      path: ./${WC_DIR}/out-of-band
      postBuild:
        substitute:
          cluster_name: "${WC_NAME}"
          organization: "\${organization}"
      prune: true
      retryInterval: 1m
      sourceRef:
        kind: GitRepository
        name: ${GITOPS_REPO}
        namespace: default
      timeout: 2m
    EOF
    ```

    It has no `serviceAccountName`. With a `kubeConfig`, Flux would impersonate that ServiceAccount in the workload
    cluster, so the kubeconfig's own rights would no longer apply. The [teams](./teams.md) tutorial uses exactly that
    to fence a team in.

    To keep SOPS-encrypted files in `out-of-band`, give it the same `decryption` as the cluster's `Kustomization`, see
    [Decrypt a cluster's files](../../how-to/sops.md#decrypt-a-clusters-files).

1. List it in the organisation's clusters, then commit and push:

    ```sh
    yq -i '.resources += ["'"${WC_NAME}"'-direct.yaml"]' ${ORG_DIR}/workload-clusters/kustomization.yaml
    git add ${WC_DIR}/out-of-band ${ORG_DIR}/workload-clusters
    git commit -m "Apply out-of-band resources to ${WC_NAME}" && git push
    ```

**Check:** the `-direct` `Kustomization` is `Ready`, and the ConfigMap is in the workload cluster:

```sh
flux get kustomizations ${MC_NAME}-clusters-${WC_NAME}-direct -n org-${ORG_NAME}
kubectl --context ${WC_CONTEXT} get configmap hello-from-out-of-band -n default -o jsonpath='{.data.values}'
```

Until the cluster is up, its kubeconfig Secret doesn't exist and the `-direct` `Kustomization` reports that it can't
read it. It retries every `retryInterval`, and gets `Ready` once the Secret is there.

Before you delete the cluster, take its out-of-band objects away first, while Flux can still reach the cluster, see
[Remove out-of-band resources](../../how-to/delete-cluster.md#remove-out-of-band-resources).

## Run Flux in the workload cluster

Some of what you deliver through `out-of-band` is itself for Flux: a [team](./teams.md) whose Flux runs in the
workload cluster gets its `GitRepository` and `Kustomization` there, and something in the workload cluster has to
reconcile them. That's Flux in the workload cluster. The `-direct` `Kustomization` still delivers `out-of-band`, and
Flux in the workload cluster reconciles the Flux objects in it. It gets no `Kustomization` of its own for
`out-of-band`.

Giant Swarm ships Flux as the `flux-app` chart, and you install it like any other app, from the cluster's `apps`, as
the [out-of-band-flux-app](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/flux/helm-release.yaml)
example does. The cost is a Flux installation in every such cluster to keep up to date.

1. Export the chart version, from the [flux-app releases](https://github.com/giantswarm/flux-app/releases), and the
   app's directory:

    ```sh
    export FLUX_APP_VERSION=FLUX_APP_VERSION
    export FLUX_DIR=${WC_DIR}/apps/flux
    mkdir -p ${FLUX_DIR}
    ```

1. Create the app's `OCIRepository` and `HelmRelease`. flux-app installs into the `flux-app` namespace of the workload
   cluster, and brings Flux's CRDs with it:

    ```sh
    cat <<EOF > ${FLUX_DIR}/oci-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-flux
      namespace: org-\${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        tag: ${FLUX_APP_VERSION}
      url: oci://gsoci.azurecr.io/charts/giantswarm/flux-app
    EOF
    cat <<'EOF' > ${FLUX_DIR}/helm-release.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      labels:
        giantswarm.io/cluster: ${cluster_name}
      name: ${cluster_name}-flux
      namespace: org-${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: ${cluster_name}-flux
        namespace: org-${organization}
      install:
        createNamespace: true
        remediation:
          remediateLastFailure: false
          retries: 10
      interval: 5m
      kubeConfig:
        secretRef:
          name: ${cluster_name}-kubeconfig
      releaseName: flux
      storageNamespace: flux-app
      targetNamespace: flux-app
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
        - kind: ConfigMap
          name: ${cluster_name}-flux-app-user-values
          optional: true
          valuesKey: values
        - kind: Secret
          name: ${cluster_name}-flux-app-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

    Both of the cluster's own layers are optional: Flux in the workload cluster needs no values to reconcile what
    `-direct` delivers. flux-app can also pull a repository of its own, with `sources` and `kustomizations` in its
    values. Their credentials belong in the `${cluster_name}-flux-app-user-secrets` Secret, written from your own
    secret manager or encrypted with SOPS, see [Encrypt an app's values](../../how-to/sops.md#encrypt-an-apps-values):
    the basic tutorial's stand-in store keeps its data in plain text in Git, so it can't hold a real token.

1. List the files in the cluster's apps, then commit and push:

    ```sh
    yq -i '.resources += ["flux/oci-repository.yaml", "flux/helm-release.yaml"]' ${WC_DIR}/apps/kustomization.yaml
    git add ${WC_DIR}/apps && git commit -m "Run Flux in ${WC_NAME}" && git push
    ```

**Check:** the release is `Ready` on the management cluster, and Flux runs in the workload cluster:

```sh
flux get helmreleases ${WC_NAME}-flux -n org-${ORG_NAME}
flux --context ${WC_CONTEXT} check
```

The `-direct` `Kustomization` stays as it is, and keeps delivering `out-of-band`.

## Next steps

- [Teams](./teams.md): give an application team its own repository, through `out-of-band`.
- [Delete a cluster](../../how-to/delete-cluster.md): what to remove, and in which order, when a cluster has
  out-of-band resources.
- [`cluster`, `apps` and `[out-of-band]`](../../reference/repo-structure.md#cluster-apps-and-out-of-band): the rules for
  each directory.
