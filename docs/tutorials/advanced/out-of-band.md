# Out-of-band resources

Everything you've built so far lives on the management cluster. A cluster is a `HelmRelease` there, an app is an
`OCIRepository` and a `HelmRelease` there, and the workload cluster only ever sees what those charts install. That
covers most things, but not all. Sometimes you want a plain object inside the workload cluster: a namespace and a
`RoleBinding` for a team, a ConfigMap an app reads, a policy. Wrapping each of those in a chart of its own is a lot of
packaging for a two-line object.

Those go into the cluster's `out-of-band` directory, and get applied straight to the workload cluster. This tutorial
adds one to the cluster from the [basic tutorial](../basic/getting-started.md), first with Flux on the management
cluster reaching into the workload cluster, then with Flux running in the workload cluster itself.

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
leave it out. Something else has to apply it to the workload cluster, and there are two ways:

1. a third Flux `Kustomization` on the management cluster, the cluster's `-direct` one, applies it through the
   cluster's kubeconfig Secret, as the
   [out-of-band-no-flux](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/)
   example does;
1. Flux in the workload cluster applies it, as the
   [out-of-band-flux-app](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/)
   example does.

Pick one of them to apply the directory. If both apply it, two Flux installations fight over the same objects.

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

A legacy cluster keeps its kubeconfig Secret in `default` instead. Its
`-direct` `Kustomization` goes in the organisation's directory, with `namespace: default`, `organization: "ORG_NAME"`
and no `dependsOn`, listed in the organisation's `kustomization.yaml`, so that the management cluster's `Kustomization`
applies it. You may also have to set `key: kubeConfig` under `kubeConfig.secretRef`, to tell Flux which key of the
Secret holds the kubeconfig.

Before you delete the cluster, take its out-of-band objects away first, while Flux can still reach the cluster, see
[Remove out-of-band resources](../../how-to/delete-cluster.md#remove-out-of-band-resources).

## Run Flux in the workload cluster

The other way is to run Flux in the workload cluster and point it at the same directory. The workload cluster then
pulls its own out-of-band objects from Git, keeps going when the management cluster is unavailable, and shows their
state where the cluster's users look. The cost is a Flux installation in every such cluster to keep up to date.

Giant Swarm ships Flux as the `flux-app` chart, and you install it like any other app, from the cluster's `apps`. This
section replaces the `-direct` `Kustomization` above: one or the other, not both.

1. Take the `-direct` `Kustomization` out, if you added it:

    ```sh
    git rm -q ${ORG_DIR}/workload-clusters/${WC_NAME}-direct.yaml
    yq -i 'del(.resources[] | select(. == "'"${WC_NAME}"'-direct.yaml"))' ${ORG_DIR}/workload-clusters/kustomization.yaml
    ```

    Flux on the management cluster then prunes what it applied, so the ConfigMap goes, until Flux in the workload
    cluster puts it back.

1. Export the chart version, from the [flux-app releases](https://github.com/giantswarm/flux-app/releases), and the
   app's directory:

    ```sh
    export FLUX_APP_VERSION=FLUX_APP_VERSION
    export FLUX_DIR=${WC_DIR}/apps/flux
    mkdir -p ${FLUX_DIR}
    ```

1. Create the app's `OCIRepository` and `HelmRelease`. flux-app installs into the `flux-app` namespace of the workload
   cluster:

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
          valuesKey: values
        - kind: Secret
          name: ${cluster_name}-flux-app-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

1. Tell Flux in the workload cluster what to apply: a `Kustomization` with the cluster's `out-of-band` directory as its
   path, from a source named `gitops`:

    ```sh
    cat <<EOF > ${FLUX_DIR}/configmap.yaml
    apiVersion: v1
    data:
      values: |-
        kustomizations:
        - name: out-of-band
          interval: 10m
          path: "./${WC_DIR}/out-of-band"
          postBuild:
            substitute:
              cluster_name: "\${cluster_name}"
              organization: "\${organization}"
          prune: true
          source_name: gitops
    kind: ConfigMap
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-flux-app-user-values
      namespace: org-\${organization}
    EOF
    ```

1. The source is your repository, and Flux in the workload cluster needs credentials to read it: flux-app writes each
   source's `credentials`, a `username` and a `password`, into a Secret next to its `GitRepository`. Credentials don't
   belong in a ConfigMap, so the source goes into the `${cluster_name}-flux-app-user-secrets` Secret, which the
   `HelmRelease` reads last. Store these values in your secret manager, with a token that can read the repository:

    ```yaml
    sources:
      - name: gitops
        interval: 1m
        branch: main
        url: https://github.com/YOUR_ORG/YOUR_REPO
        provider: github
        credentials:
          username: git
          password: YOUR_TOKEN
    ```

    Then have ESO write them into the Secret, through the organisation's store from the basic tutorial:

    ```sh
    cat <<EOF > ${FLUX_DIR}/externalsecret.yaml
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: \${cluster_name}-flux-app-user-secrets
      namespace: org-\${organization}
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: SecretStore
        name: ${SECRET_STORE}
      target:
        name: \${cluster_name}-flux-app-user-secrets
        template:
          metadata:
            labels:
              reconcile.fluxcd.io/watch: Enabled
      data:
        - secretKey: values
          remoteRef:
            key: gitops/flux-app-sources
    EOF
    ```

    Put the name of your secret in `key`. If you keep the cluster's secrets in the repository with SOPS instead,
    write the Secret with the same `values` key and encrypt it, see
    [Encrypt an app's values](../../how-to/sops.md#encrypt-an-apps-values), and list that file below instead. Until the
    Secret exists, flux-app installs without a source, and its `Kustomization` waits for one. The
    [example](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/flux/configmap.yaml)
    keeps a made-up source in its ConfigMap instead, which is fine for an example and nothing else.

1. List the files in the cluster's apps, then commit and push:

    ```sh
    yq -i '.resources += ["flux/oci-repository.yaml", "flux/helm-release.yaml", "flux/configmap.yaml",
      "flux/externalsecret.yaml"]' ${WC_DIR}/apps/kustomization.yaml
    git add ${WC_DIR}/apps ${ORG_DIR}/workload-clusters
    git commit -m "Run Flux in ${WC_NAME} for its out-of-band resources" && git push
    ```

**Check:** the release is `Ready` on the management cluster, and Flux in the workload cluster reconciles the directory:

```sh
flux get helmreleases ${WC_NAME}-flux -n org-${ORG_NAME}
flux --context ${WC_CONTEXT} get kustomizations -A
```

The `postBuild` gives Flux in the workload cluster the same variables the `-direct` `Kustomization` had: the cluster's
apps `Kustomization` fills in `${cluster_name}` and `${organization}` in the ConfigMap, and flux-app passes them on.
For SOPS-encrypted files in `out-of-band`, flux-app takes the private keys in its `sopsEncryption` values, which belong
in the `-user-secrets` Secret too.

## Next steps

- [Teams](./teams.md): give an application team its own repository, through `out-of-band`.
- [Delete a cluster](../../how-to/delete-cluster.md): what to remove, and in which order, when a cluster has
  out-of-band resources.
- [`cluster`, `apps` and `[out-of-band]`](../../reference/repo-structure.md#cluster-apps-and-out-of-band): the rules for
  each directory.
