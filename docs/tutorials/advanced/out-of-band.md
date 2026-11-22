# Out-of-band resources

Everything you've built so far lives on the management cluster. A cluster is a `HelmRelease` there, an app is an
`OCIRepository` and a `HelmRelease` there, and the workload cluster only ever sees what those charts install. That
covers most things, but not all. Sometimes you want a plain object inside the workload cluster: a namespace and a
`RoleBinding` for a team, a ConfigMap an app reads, a policy. Wrapping each of those in a chart of its own is a lot of
packaging for a two-line object.

Those go into the cluster's `out-of-band` directory, and get applied straight to the workload cluster. This tutorial
adds one to the cluster from the [basic tutorial](../basic/getting-started.md), and has Flux on the management cluster
push it there. Then it shows the other way round, where the workload cluster's own Flux pulls its `out-of-band`
directory, on a cluster of its own. That second half creates a second workload cluster, the same size as the first,
which [Clean up](#clean-up) deletes again.

- [When to apply directly](#when-to-apply-directly)
- [Add the out-of-band directory](#add-the-out-of-band-directory)
- [Add the -direct `Kustomization`](#add-the--direct-kustomization)
- [Run Flux in the workload cluster](#run-flux-in-the-workload-cluster)
- [Clean up](#clean-up)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## When to apply directly

Reach for `out-of-band` when the object belongs in the workload cluster and no chart installs it: namespaces,
`RoleBinding`s, ConfigMaps and Secrets that workloads read, policies, or the `GitRepository` and `Kustomization` of a
[team](./teams.md) whose Flux runs in the workload cluster. When a chart exists for the thing, prefer an app: Helm
tracks its objects and its version, and the cluster's apps wait for the cluster to be ready.

Everything in `${WC_DIR}/cluster` and `${WC_DIR}/apps` is applied to the management cluster. `${WC_DIR}/out-of-band`
never is: `${WC_DIR}/kustomization.yaml` lists `cluster/` or `apps/`, never `out-of-band/`, so the cluster's
`Kustomization`s leave it out. Something else has to apply it to the workload cluster, and that has two facets:

- **Push.** A Flux `Kustomization` on the management cluster applies `out-of-band` through the workload cluster's
  kubeconfig Secret, as in the
  [out-of-band-no-flux](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/)
  example. The workload cluster needs nothing installed for it, and the management cluster shows the result next to
  the cluster's other `Kustomization`s.
- **Pull.** The workload cluster's own Flux reconciles `out-of-band` from Git, as in the
  [out-of-band-flux-app](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/)
  example. Delivery goes on while the management cluster is unavailable, and the cluster's users see the state where
  they work, at the cost of a Flux installation in the cluster to keep up to date.

Use one of them for a cluster's `out-of-band` directory, never both: two Flux installations applying the same
directory to the same cluster fight over the same objects.

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

1. Check that `${WC_DIR}/kustomization.yaml` doesn't list `out-of-band/`: `${WC_DIR}/out-of-band` must never be applied
   to the management cluster:

    ```sh
    yq '.resources' ${WC_DIR}/kustomization.yaml
    ```

The directory needs no `kustomization.yaml`: Flux applies every YAML file in it, and in the directories below it. Add
one if you want to list the files, or patch them.

## Add the -direct `Kustomization`

This is the push facet: the `Kustomization` that applies `out-of-band` through the cluster's kubeconfig, which the
template names `*-direct`. The template's suffixes, such as `-direct`, `-apps` and `-from-template`, are only labels to
tell the techniques apart, so name yours however you like. This tutorial keeps `-direct`, so that its commands match
the examples.

It applies `out-of-band` with the cluster's kubeconfig Secret, `${WC_NAME}-kubeconfig`, which the management cluster
creates in `org-${ORG_NAME}` once the cluster is up. A `Kustomization` reads its kubeconfig Secret from its own
namespace, so it goes in the organisation's `workload-clusters`, next to the cluster's other two: the organisation's
namespace `Kustomization` applies it into `org-${ORG_NAME}`.

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

If it doesn't get there, see [When something isn't Ready](../../how-to/troubleshooting.md).

Until the cluster is up, its kubeconfig Secret doesn't exist and the `-direct` `Kustomization` reports that it can't
read it. It retries every `retryInterval`, and gets `Ready` once the Secret is there.

Before you delete the cluster, take its out-of-band objects away first, while Flux can still reach the cluster, see
[Remove out-of-band resources](../../how-to/delete-cluster.md#remove-out-of-band-resources).

## Run Flux in the workload cluster

This is the pull facet: the workload cluster runs Flux, and that Flux reconciles the cluster's `out-of-band` directory
itself. Set it up on a cluster of its own, one with no `-direct` `Kustomization`, not on the cluster you've just given
one. The [out-of-band-flux-app](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/)
example is such a cluster: flux-app in its `apps`, and its `out-of-band` directory, with no `-direct` `Kustomization`.

Giant Swarm ships Flux as the `flux-app` chart, and you install it like any other app, from the cluster's `apps`.
Flux in a workload cluster is also what reconciles the Flux objects that a push delivers, such as the `GitRepository`
and `Kustomization` of a [team](./teams.md#add-a-team-with-flux-in-the-workload-cluster): that needs steps 2 and 3
below, and none of the others.

1. Create the second cluster as in
   [3. Create a workload cluster](../basic/getting-started.md#3-create-a-workload-cluster) of the basic tutorial. That
   gives it its `apps` directory and its apps `Kustomization`. Run that step in a new shell, with `WC_NAME` and
   `WC_DIR` exported for the second cluster, so that this shell keeps your first cluster's, and come back once it's
   pushed. Then export its name and directory here:

    ```sh
    export FLUX_WC_NAME=CLUSTER_NAME
    export FLUX_WC_DIR=${ORG_DIR}/workload-clusters/${FLUX_WC_NAME}
    ```

1. Export the chart version, from the [flux-app releases](https://github.com/giantswarm/flux-app/releases), and the
   app's directory:

    ```sh
    export FLUX_APP_VERSION=FLUX_APP_VERSION
    export FLUX_DIR=${FLUX_WC_DIR}/apps/flux
    mkdir -p ${FLUX_DIR}
    ```

1. Create the app's `OCIRepository` and `HelmRelease`, and list them in the cluster's apps. flux-app installs into the
   `flux-app` namespace of the workload cluster, and brings Flux's CRDs with it:

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
    yq -i '.resources += ["flux/oci-repository.yaml", "flux/helm-release.yaml"]' ${FLUX_WC_DIR}/apps/kustomization.yaml
    ```

    Both of the cluster's own values layers are optional, so Flux installs without them, and reconciles nothing of its
    own yet.

1. Give the cluster's `out-of-band` directory, `${FLUX_WC_DIR}/out-of-band`, something to apply, as in
   [Add the out-of-band directory](#add-the-out-of-band-directory):

    ```sh
    mkdir -p ${FLUX_WC_DIR}/out-of-band/configmaps
    cat <<'EOF' > ${FLUX_WC_DIR}/out-of-band/configmaps/configmap.yaml
    apiVersion: v1
    data:
      values: |-
        I am the ${cluster_name} cluster, and my own Flux pulled me in.
    kind: ConfigMap
    metadata:
      name: hello-from-out-of-band
      namespace: default
    EOF
    ```

    `${FLUX_WC_DIR}/kustomization.yaml`, from the basic tutorial, lists only `apps/`, so the management cluster never
    applies this directory.

1. Point Flux in the workload cluster at `${FLUX_WC_DIR}/out-of-band`. flux-app takes a list of `sources`, your
   repository, and of `kustomizations`, what to apply from them. The `Kustomization` goes into a ConfigMap. The
   cluster's apps `Kustomization` fills in `${cluster_name}` and `${organization}` in it, and `postBuild` passes them
   on to Flux in the workload cluster, so `out-of-band` gets the same variables as with a push:

    ```sh
    cat <<EOF > ${FLUX_DIR}/configmap.yaml
    apiVersion: v1
    data:
      values: |-
        kustomizations:
        - name: out-of-band
          interval: 10m
          path: "./${FLUX_WC_DIR}/out-of-band"
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
    yq -i '.resources += ["flux/configmap.yaml"]' ${FLUX_WC_DIR}/apps/kustomization.yaml
    ```

1. Give Flux in the workload cluster a way into your repository. flux-app takes the list of `sources` from its values,
   and the source needs credentials, so it belongs in the `${cluster_name}-flux-app-user-secrets` Secret, which the
   `HelmRelease` reads last. Create a GitHub token for it, as you did for the management cluster in
   [step 1](../basic/getting-started.md#1-connect-the-management-cluster) of the basic tutorial, with one more
   permission: flux-app also writes a GitHub `Provider` and an `Alert` from the same credentials, which report each of
   its `Kustomization`s as a commit status. So the token needs read access to the repository's contents, and read and
   write access to commit statuses if you want those statuses; without it, the `Alert` logs errors and Flux carries on.

   This tutorial keeps the Secret in the repository, encrypted with SOPS, which needs a key for the cluster and its
   apps `Kustomization` set to decrypt with it. Add an age key, as
   [Add a workload cluster key (age)](../../how-to/sops.md#add-a-workload-cluster-key-age) describes, and give both of
   the cluster's `Kustomization`s the `decryption` of
   [Decrypt a cluster's files](../../how-to/sops.md#decrypt-a-clusters-files), with `sops-age-${FLUX_WC_NAME}`. Those
   pages use `WC_NAME`, so run them with `WC_NAME=${FLUX_WC_NAME}`, in the shell you created the cluster in, for
   example, and come back to this one. If you keep your secrets in a secret manager instead, write the same Secret
   with an `ExternalSecret`, see [Read secrets from a secret manager](../../how-to/external-secrets.md). The basic
   tutorial's stand-in store keeps its data in plain text in Git, so it can't hold a real token.

1. Write the Secret, encrypted on its way to the file, so the token never lands in the working tree in plain text.
   Read the token without it landing in your shell history:

    ```sh
    read -rs FLUX_WC_TOKEN
    cat <<EOF | sops --encrypt --filename-override ${FLUX_DIR}/secret.enc.yaml --input-type yaml --output-type yaml \
      /dev/stdin > ${FLUX_DIR}/secret.enc.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      labels:
        reconcile.fluxcd.io/watch: Enabled
      name: \${cluster_name}-flux-app-user-secrets
      namespace: org-\${organization}
    stringData:
      values: |
        sources:
          - name: gitops
            interval: 1m
            branch: main
            url: ${GITOPS_REPO_URL}
            provider: github
            credentials:
              username: git
              password: ${FLUX_WC_TOKEN}
    EOF
    unset FLUX_WC_TOKEN
    yq -i '.resources += ["flux/secret.enc.yaml"]' ${FLUX_WC_DIR}/apps/kustomization.yaml
    ```

    `--filename-override` makes `sops` pick the rule for the file's path in `.sops.yaml`, and the command needs
    `sops` 3.10.0 or newer (see [Tools](../../reference/tools.md#tools)). If `sops` finds no rule, it fails and
    leaves the file empty, never in plain text. The source's `name` is the `source_name` of the `Kustomization` in
    the ConfigMap above. The example cluster keeps a made-up source in its ConfigMap instead, which is fine for an
    example and nothing else.

1. Commit and push:

    ```sh
    git add ${FLUX_WC_DIR}
    git commit -m "Pull out-of-band resources with Flux in ${FLUX_WC_NAME}" && git push
    ```

**Check:** the release is `Ready` on the management cluster, and Flux in the workload cluster reconciles `out-of-band`:

```sh
flux get helmreleases -n org-${ORG_NAME} | grep -- -flux
flux --context FLUX_WC_CONTEXT check -n flux-app
flux --context FLUX_WC_CONTEXT get kustomizations -n flux-app
```

If it doesn't get there, see [When something isn't Ready](../../how-to/troubleshooting.md).

`FLUX_WC_CONTEXT` is that cluster's context, from `kubectl gs login`, as in the basic tutorial.

## Clean up

Delete the second cluster, the one that runs Flux, as [Delete a workload cluster](../../how-to/delete-cluster.md)
describes, with `WC_NAME` set to `${FLUX_WC_NAME}`. It has a SOPS key and out-of-band resources, so follow the whole
page, including [Remove out-of-band resources](../../how-to/delete-cluster.md#remove-out-of-band-resources). Keep the
first cluster if you're going on to [Teams](./teams.md): it uses that cluster's `-direct` `Kustomization`.

## Next steps

- [Teams](./teams.md): give an application team its own repository, through `out-of-band`.
- [Delete a cluster](../../how-to/delete-cluster.md): what to remove, and in which order, when a cluster has
  out-of-band resources.
- [`cluster`, `apps` and `[out-of-band]`](../../reference/repo-structure.md#cluster-apps-and-out-of-band): the rules for
  each directory.
