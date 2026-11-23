# Add an app to a cluster

An app is a Flux `HelmRelease` that installs a Helm chart into the workload cluster, and an `OCIRepository` that
points at the chart. Both live on the management cluster, in the organisation's namespace, in a directory of the app's
own under the cluster's `apps`. This page adds one, either written out in full or from an App Template that already
holds the app's defaults.

The app's directory comes in one of two layouts:

- **Files listed one by one.** The directory holds only the app's manifests, and the cluster's
  `apps/kustomization.yaml` lists each file. It fits an app written out in full whose values, if it has any, are a
  plain ConfigMap or Secret file next to it. `kubectl gs gitops add app` writes this layout.
- **A `kustomization.yaml` of the app's own**, and the cluster's list names the directory. An app from an App Template
  or a stack needs it, to list the base and patch it. So does an app whose values a `configMapGenerator` makes from
  `override_config.yaml`, as the steps below do.

The [basic tutorial](../tutorials/basic/getting-started.md#4-deploy-an-app) walks through a first app step by step, and
[Reuse an app's configuration](../tutorials/intermediate/app-templates.md) explains App Templates. Examples:

- an app with its values in the `HelmRelease`, its files listed one by one in the cluster's
  [apps/kustomization.yaml](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/kustomization.yaml):
  [WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world/);
- an app from an App Template, with a `kustomization.yaml` of its own:
  [apps/hello-world-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-from-template/);
- base apps from a [stack](../tutorials/intermediate/stacks.md), with plain and SOPS-encrypted overrides:
  [cluster/apps/envoy-gateway-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/cluster/apps/envoy-gateway-from-template/).

Export the names the commands use, then create the app's directory and go into it:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
mkdir -p management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

`APP_NAME` goes into the names of the app's resources. They all get the `${cluster_name}-` prefix, so you can deploy
the same app to several clusters of an organisation. When you use an App Template, `APP_NAME` has to be the app name the
template uses, for example `hello-world` for [bases/apps/hello-world](/bases/apps/hello-world/).

`kubectl gs gitops add app` used to write these files, and `kubectl gs deploy chart --dry-run` prints an
`OCIRepository` and a `HelmRelease` you can start from. `gitops add app` is deprecated, with no replacement. Both
commands write something different from this page: no cluster values, and a literal cluster name instead of
`${cluster_name}`. [App](./kubectl-gs.md#app) shows what they write and how to get from it to the `HelmRelease` below.

## Add an app directly

The app's `HelmRelease` reads its values in layers, listed in `spec.valuesFrom`. First come the cluster's values,
which the management cluster creates for every cluster. Then come two optional layers of your own: the `-user-values`
ConfigMap and the `-user-secrets` Secret. The cluster values come first so that the chart knows the cluster's
`baseDomain`, `provider` and the like, and so that your values can override them (see
[App values](../reference/values.md#app-values)).

1. Set the chart, its version and the namespace it goes into:

    ```sh
    export APP_CHART=APP_CHART
    export APP_VERSION=APP_VERSION
    export APP_NAMESPACE=APP_NAMESPACE
    ```

    `APP_CHART` is the chart's name in the registry, for example `hello-world`, `APP_VERSION` its version (the OCI
    tag), and `APP_NAMESPACE` the namespace in the workload cluster the app is installed into.

1. Create the `OCIRepository` that points at the chart. The example uses the Giant Swarm catalogue; change the `url` to
   use a chart from another registry:

    ```sh
    cat <<EOF > oci-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        tag: ${APP_VERSION}
      url: oci://gsoci.azurecr.io/charts/giantswarm/${APP_CHART}
    EOF
    ```

1. Create the `HelmRelease` that installs the chart into the workload cluster through the cluster's kubeconfig Secret.
   It creates the target namespace, which a new cluster doesn't have, and retries a failed install or upgrade:

    ```sh
    cat <<EOF > helm-release.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      labels:
        giantswarm.io/cluster: \${cluster_name}
      name: \${cluster_name}-${APP_NAME}
      namespace: org-\${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: \${cluster_name}-${APP_NAME}
        namespace: org-\${organization}
      install:
        createNamespace: true
        remediation:
          remediateLastFailure: false
          retries: 10
      interval: 5m
      kubeConfig:
        secretRef:
          name: \${cluster_name}-kubeconfig
      releaseName: ${APP_NAME}
      storageNamespace: ${APP_NAMESPACE}
      targetNamespace: ${APP_NAMESPACE}
      timeout: 10m
      upgrade:
        remediation:
          remediateLastFailure: true
          retries: 10
          strategy: rollback
      valuesFrom:
        - kind: ConfigMap
          name: \${cluster_name}-cluster-values
          valuesKey: values
        - kind: ConfigMap
          name: \${cluster_name}-${APP_NAME}-user-values
          optional: true
          valuesKey: values
        - kind: Secret
          name: \${cluster_name}-${APP_NAME}-user-secrets
          optional: true
          valuesKey: values
    EOF
    ```

1. If the app needs values, put them in `override_config.yaml`:

    ```sh
    cat <<EOF > override_config.yaml
    # values of the ${APP_CHART} chart for this cluster
    EOF
    ```

1. Create the app's `kustomization.yaml`. Its `configMapGenerator` turns `override_config.yaml` into the
   `-user-values` ConfigMap, with the label that makes Flux apply a change at once; leave it out if you didn't create
   the file. An app without values doesn't need this file: you can list its files one by one instead (see
   [List the app in the cluster](#list-the-app-in-the-cluster)):

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: \${cluster_name}-${APP_NAME}-user-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    namespace: org-\${organization}
    resources:
      - helm-release.yaml
      - oci-repository.yaml
    EOF
    ```

1. For secret values, add the `-user-secrets` Secret. It can be an `ExternalSecret` that reads it from your secret
   manager ([Give an app secret values](./external-secrets.md#give-an-app-secret-values)), or a SOPS-encrypted
   `secret.enc.yaml` ([Encrypt an app's values](./sops.md#encrypt-an-apps-values)).

1. Continue with [List the app in the cluster](#list-the-app-in-the-cluster).

## Add an app from an App Template

An App Template in [`bases/apps`](/bases/apps/) holds the app's `OCIRepository`, `HelmRelease` and default values. The
cluster's directory only lists it and adds what's different for the cluster.

1. Pick the template and export its path. `APP_NAME` has to be the app name the template uses:

    ```sh
    export APP_TEMPLATE_DIR=bases/apps/APP_TEMPLATE
    ```

1. If the cluster needs other values than the template's defaults, put the ones to change into
   `override_config.yaml`. Only the keys you set change; the rest still comes from the template:

    ```sh
    cat <<EOF > override_config.yaml
    # values to change for this cluster
    EOF
    ```

1. Create the app's `kustomization.yaml`. Leave out the block between the comments if you didn't create
   `override_config.yaml`:

    ```sh
    cat <<EOF > kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    ## CONFIGURATION OVERRIDE BLOCK START - include only if overriding the template's values
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: \${cluster_name}-${APP_NAME}-user-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    ## CONFIGURATION OVERRIDE BLOCK END
    kind: Kustomization
    namespace: org-\${organization}
    resources:
      - ../../../../../../../../${APP_TEMPLATE_DIR}
    EOF
    ```

    No patch is needed: the template's `HelmRelease` already lists the `-user-values` ConfigMap and the `-user-secrets`
    Secret as optional layers in `spec.valuesFrom`, so creating them is enough. Secret values go in the same way as for
    an app added directly.

1. To change anything else for this cluster, patch it in the same `kustomization.yaml`. For example, to install
   another chart version, patch the `OCIRepository`. The `$` of the target name is escaped, as kustomize reads the
   name as a regular expression:

    ```yaml
    patches:
      - patch: |-
          - op: replace
            path: /spec/ref/tag
            value: "NEW_VERSION"
        target:
          kind: OCIRepository
          name: \${cluster_name}-hello-world
    ```

    A patch also orders the app after a release of another base it needs. `hello-world` needs the Gateway API CRDs,
    so in a cluster that has the [envoy-gateway](/bases/stacks/envoy-gateway/) stack, add
    `${cluster_name}-gateway-api-crds` to its `dependsOn` (see
    [Order it after another release](../tutorials/intermediate/app-templates.md#order-it-after-another-release)).

1. Continue with [List the app in the cluster](#list-the-app-in-the-cluster).

## Make it a base app

The steps above add a secondary app, in `apps`. The Flux `Kustomization` for the cluster's apps, `WC_NAME-apps.yaml`,
applies it once the cluster is ready. A base app is one the cluster needs from the start. It goes in `cluster/apps`,
and the cluster's own `Kustomization`, `WC_NAME.yaml`, applies it with the cluster, so its `HelmRelease` installs as
soon as the cluster can take it.
[Base apps and secondary apps](../explanation/how-it-works.md#base-apps-and-secondary-apps) explains the difference.

1. Put the app's directory in `cluster/apps` instead of `apps`. It's one level deeper, so a path to an App Template
   or a stack needs one more `../`:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}
    mkdir -p cluster/apps
    git mv apps/${APP_NAME} cluster/apps/${APP_NAME}
    yq -i '.resources |= map(sub("^\.\./"; "../../"))' cluster/apps/${APP_NAME}/kustomization.yaml
    ```

1. List it in `cluster/apps/kustomization.yaml`, and list `apps/` in `cluster/kustomization.yaml` if it isn't there
   yet:

    ```sh
    [ -f cluster/apps/kustomization.yaml ] || cat <<'EOF' > cluster/apps/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources: []
    EOF
    yq -i '.resources += ["'"${APP_NAME}"'"]' cluster/apps/kustomization.yaml
    yq -i '.resources |= ((. // []) + ["apps/"] | unique)' cluster/kustomization.yaml
    ```

1. Take it out of `apps/kustomization.yaml` if you listed it there.

Moving an app between `apps` and `cluster/apps` on a running cluster moves it from one `Kustomization` to the other.
Do both in one commit: the objects keep their names, so Flux updates them in place instead of reinstalling the app.

If the cluster has a single `Kustomization` for its whole directory, split it first (see
[Flux `Kustomization`s](../reference/repo-structure.md#flux-kustomizations)).

## Pull the chart from a private registry

Charts from the Giant Swarm catalogue are public. If your chart is in a private registry, give the `OCIRepository`
credentials to read it. They go in a Secret in the organisation's namespace, next to the `OCIRepository`. The Secret
holds a credential, so keep it out of Git in plain text: encrypt it with the cluster's SOPS key, as the steps below do,
or have an `ExternalSecret` write it from your secret manager (see
[Read secrets from a secret manager](./external-secrets.md)).

1. Export the path to a Docker registry config with the credentials:

    ```sh
    export DOCKER_CONFIG_JSON=PATH
    ```

1. In the app's directory, create the Secret and save it to a file, encrypted with the cluster's key. `sops`
   encrypts it on its way into the file, so the credentials never sit in the repository in plain text. The cluster's
   rule in `.sops.yaml` picks the key. If the cluster has no key yet, add one first (see
   [Add a workload cluster key (GPG)](./sops.md#add-a-workload-cluster-key-gpg)). For a GPG key, import its public key
   first; an age key needs nothing:

    ```sh
    gpg --import "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc"
    kubectl create secret docker-registry \
    ${WC_NAME}-${APP_NAME}-pull-secret \
    --namespace org-${ORG_NAME} \
    --from-file .dockerconfigjson=${DOCKER_CONFIG_JSON} \
    --dry-run=client \
    -o yaml | sops --encrypt --filename-override pullsecret.enc.yaml /dev/stdin > pullsecret.enc.yaml
    ```

    `--filename-override` tells `sops` which file it's writing, and so which rule applies, as it reads the Secret from
    stdin. It needs `sops` 3.10.0 or newer, see [Tools](../reference/tools.md#tools).

1. Reference the Secret in the `OCIRepository`, and list it: in the app's `kustomization.yaml` if it has one, or as
   `APP_NAME/pullsecret.enc.yaml` in the cluster's `apps/kustomization.yaml` if that lists the app's files one by one:

    ```sh
    yq -i ".spec.secretRef.name = \"${WC_NAME}-${APP_NAME}-pull-secret\"" oci-repository.yaml
    if [ -f kustomization.yaml ]; then
      yq -i '.resources += ["pullsecret.enc.yaml"]' kustomization.yaml
    else
      yq -i '.resources += ["'"${APP_NAME}"'/pullsecret.enc.yaml"]' ../kustomization.yaml
    fi
    ```

For an app from an App Template, set `secretRef` with a patch of the template's `OCIRepository`, as for the version
above.

## List the app in the cluster

1. Go back to the cluster's `apps` directory:

    ```sh
    cd ..
    ```

1. Add the app to the resources of the `kustomization.yaml` there. If the app has a `kustomization.yaml` of its own,
   list its directory:

    ```sh
    yq -i ".resources += \"${APP_NAME}\" | .resources style=\"\"" kustomization.yaml
    ```

    If it hasn't, list each of its files instead:

    ```sh
    for f in ${APP_NAME}/*.yaml; do yq -i ".resources += \"${f}\"" kustomization.yaml; done
    ```

1. Commit and push. Once the cluster is ready, the cluster's apps `Kustomization` applies the app.

**Check:** the release is `Ready` on the management cluster:

```sh
flux get helmreleases ${WC_NAME}-${APP_NAME} -n org-${ORG_NAME}
```

If it doesn't get there, see [When something isn't Ready](./troubleshooting.md).

To change the app later, see [Change an app](./update-app.md). To let Flux install new chart versions by itself, see
[Let Flux install new chart versions](../tutorials/intermediate/automatic-updates.md).
