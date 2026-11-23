# App Templates

At the end of the [basic tutorial](../basic/getting-started.md) you have one organisation, one workload cluster and
one app: hello-world, in `${WC_DIR}/apps/hello-world`, with an `OCIRepository`, a `HelmRelease`, its values and an
`ExternalSecret`, written out by hand, answering through the Envoy Gateway in `${WC_DIR}/apps/envoy-gateway`. That's
fine for one cluster. The day a second cluster wants hello-world, you
copy the directory, and from then on you have two copies of the same app that quietly drift apart, one fix at a time.

An App Template writes the app once, in `bases/apps`, with `${cluster_name}` wherever the cluster goes. Every cluster
that wants the app lists the template, and adds only what's its own: a value or two, perhaps a version. By the end of
this tutorial, hello-world is a template, your cluster runs it from there with values of its own, and you know how to
make a template wait for another release. It creates no cluster: everything happens on the one from the basic
tutorial.

- [Create the App Template](#create-the-app-template)
- [Deploy it to a cluster](#deploy-it-to-a-cluster)
- [Override values for one cluster](#override-values-for-one-cluster)
- [Order it after another release](#order-it-after-another-release)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.

## Create the App Template

Your fork already ships this template: [bases/apps/hello-world](/bases/apps/hello-world). The steps below write the
same files, without its comments, so you can follow them over the top of it, or point the exports at another chart and
build one of your own.

1. Export what the template needs. `APP_VERSION` is the chart version (the OCI tag) the template starts with; the
   fork's template pins the one Renovate last moved it to, in its `oci-repository.yaml`:

    ```sh
    export APP_NAME=hello-world
    export APP_CHART=hello-world
    export APP_VERSION=$(yq '.spec.ref.tag' bases/apps/hello-world/oci-repository.yaml)
    export APP_NAMESPACE=hello-world
    ```

    `APP_NAME` goes into the resource names and is the Helm release name, `APP_CHART` is the chart's name in the
    registry, and `APP_NAMESPACE` is the namespace in the workload cluster the app goes into.

    The chart comes from the Giant Swarm catalog, `oci://gsoci.azurecr.io/charts/giantswarm`. For a chart in another
    registry, change the `url` below.

1. Create the template's directory:

    ```sh
    mkdir -p bases/apps/${APP_NAME}
    ```

1. Create the `OCIRepository`, which says where the chart is and which version to use. The `\$` keeps
   `${cluster_name}` and `${organization}` in the file for Flux to fill in later, while the shell fills in the
   `APP_*` values now:

    ```sh
    cat <<EOF > bases/apps/${APP_NAME}/oci-repository.yaml
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

1. Create the `HelmRelease`, which installs the chart into the workload cluster through its kubeconfig Secret:

    ```sh
    cat <<EOF > bases/apps/${APP_NAME}/helm-release.yaml
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
          name: \${cluster_name}-${APP_NAME}-values
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

    The cluster's name is in every resource name, so two clusters of the same organisation can both have the app
    without their objects colliding in `org-${ORG_NAME}`. Flux merges the `valuesFrom` entries in order, and later
    entries win:

    1. `${cluster_name}-cluster-values`, which the management cluster creates for every workload cluster, with values
       such as `baseDomain`;
    1. `${cluster_name}-${APP_NAME}-values`, the template's defaults;
    1. `${cluster_name}-${APP_NAME}-user-values` and `${cluster_name}-${APP_NAME}-user-secrets`, a single cluster's
       own values. Both are optional, so a cluster that's happy with the defaults needs neither.

    [App values](../../reference/values.md#app-values) has the layers in full.

1. Put the template's defaults, plain Helm values, into `default_config.yaml`:

    ```sh
    cat <<'EOF' > bases/apps/${APP_NAME}/default_config.yaml
    autoscaling:
      minReplicas: 1
    ingress:
      enabled: false
    route:
      enabled: true
      kind: HTTPRoute
      parentRefs:
        - name: giantswarm-default
          namespace: envoy-gateway-system
    EOF
    ```

    hello-world gets an `HTTPRoute` on the `giantswarm-default` Gateway that Envoy Gateway serves, as in the basic
    tutorial. The template sets no hostname: the hostname has to be one of the subdomains the cluster's own Gateway
    lists, so each cluster sets its own. Secret values don't belong here: a cluster gets them through its own
    `-user-secrets` Secret, below.

1. Create the template's `kustomization.yaml`. Its `configMapGenerator` turns `default_config.yaml` into the
   `-values` ConfigMap, so the file doesn't need a ConfigMap around it. The label makes Flux upgrade the release as
   soon as the values change, rather than at its next interval:

    ```sh
    cat <<EOF > bases/apps/${APP_NAME}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
          - values=default_config.yaml
        name: \${cluster_name}-${APP_NAME}-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    resources:
      - helm-release.yaml
      - oci-repository.yaml
    EOF
    ```

That's the template. On its own it does nothing: no Flux `Kustomization` points at `bases`, so it isn't part of the
planting plan until a cluster lists it. That also means you can keep and review an app's configuration before any
cluster runs it.

The fork's copy of hello-world's template has comments that explain each part, which these steps don't write. Once
you've compared the two, put the fork's back, so they stay:

```sh
git checkout -- bases/apps/hello-world
```

If you built a template for another chart, it's a new directory, which this leaves as it is: commit it with the
cluster's change below.

## Deploy it to a cluster

Now swap your cluster's hand-written hello-world for the template. The template's objects have the same names as the
ones you wrote in the basic tutorial, `${WC_NAME}-hello-world`, and the same Flux `Kustomization`, the cluster's apps
one, applies both. So Flux updates the release in place, rather than uninstalling it and installing it again.

1. Remove the `OCIRepository` and the `HelmRelease`, which the template now brings:

    ```sh
    export APP_DIR=${WC_DIR}/apps/hello-world
    git rm -q ${APP_DIR}/oci-repository.yaml ${APP_DIR}/helm-release.yaml
    ```

    Your `override_config.yaml` stays as it is. It already fills the `${cluster_name}-hello-world-user-values`
    ConfigMap, which is the cluster's own layer in the template too, and it keeps the route's hostname,
    `hello.{{ .Values.baseDomain }}`, which the template leaves to the cluster.

1. Replace the app's `kustomization.yaml` with one that lists the template instead of the two files, and still turns
   `override_config.yaml` into the `-user-values` ConfigMap. Your hand-written `HelmRelease` waited for the Gateway API
   CRDs; the template doesn't, for reasons [Order it after another release](#order-it-after-another-release) gives,
   so a patch adds that `dependsOn` back for this cluster:

    ```sh
    cat <<'EOF' > ${APP_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    buildMetadata: [originAnnotations]
    configMapGenerator:
      - files:
          - values=override_config.yaml
        name: ${cluster_name}-hello-world-user-values
    generatorOptions:
      disableNameSuffixHash: true
      labels:
        reconcile.fluxcd.io/watch: Enabled
    kind: Kustomization
    namespace: org-${organization}
    patches:
      - patch: |-
          - op: add
            path: /spec/dependsOn
            value:
              - name: ${cluster_name}-gateway-api-crds
        target:
          kind: HelmRelease
          name: \${cluster_name}-hello-world
    resources:
      - ../../../../../../../../bases/apps/hello-world
    EOF
    ```

    Keep the `ExternalSecret` from the basic tutorial, if the app has one. It writes the `-user-secrets` Secret,
    which the template reads too:

    ```sh
    [ -f ${APP_DIR}/externalsecret.yaml ] && yq -i '.resources += ["externalsecret.yaml"]' ${APP_DIR}/kustomization.yaml
    ```

    `${WC_DIR}/apps/kustomization.yaml` already lists `hello-world`, so nothing else changes.

1. Commit and push:

    ```sh
    git add ${APP_DIR}
    git commit -m "Deploy hello-world to ${WC_NAME} from its App Template" && git push
    ```

**Check:** the release is `Ready`, with the template's chart version:

```sh
flux get helmreleases ${WC_NAME}-hello-world -n org-${ORG_NAME}
```

If it doesn't get there, see [When something isn't Ready](../../how-to/troubleshooting.md).

The page still answers at the same address, as the route didn't change, only where its values come from:

```sh
curl -s ${HELLO_URL} | head
```

The cluster now runs the version the template pins. If it ran another one before, such as the basic tutorial's
`3.2.3`, helm-controller has just moved the release to the template's chart, `3.2.4` when this was written.
The next section shows how one cluster keeps a version of its own.

## Override values for one cluster

A cluster changes a template in two ways: with values, and with patches.

Values go into the cluster's own layers, which you've just met. `override_config.yaml` is the
`${cluster_name}-hello-world-user-values` ConfigMap, so anything in it wins over the template's defaults, for this
cluster only:

```sh
yq -i '.autoscaling.minReplicas = 3' ${APP_DIR}/override_config.yaml
```

Secret values go into the `${cluster_name}-hello-world-user-secrets` Secret. Where that Secret comes from is up to
you: an `ExternalSecret` that reads your secret manager, as in the basic tutorial, or a Secret encrypted with SOPS in
the repository, see [Encrypt an app's values](../../how-to/sops.md#encrypt-an-apps-values). You can use either, or both
for different apps; neither needs the other.

Everything else about the template's objects you change with a patch in the app's `kustomization.yaml`, as you did
for `dependsOn`. kustomize applies the cluster's patches after the template's own, so the cluster's win. To keep this
cluster on a version of its own, add this to the `patches:` in `${APP_DIR}/kustomization.yaml`:

```yaml
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
        value: "VERSION"
    target:
      kind: OCIRepository
      name: \${cluster_name}-hello-world
```

`VERSION` is the chart version this cluster runs. The `# renovate:` comment lets Renovate find the version, which it
can't see in a kustomize patch otherwise. The `$` of the target name is escaped, as kustomize reads the name as a
regular expression. The [stages](./stages-and-regions.md#stages) use the same patch to give each stage its own versions.

Commit and push, and check the release again.

## Order it after another release

Some charts need something another release installs first, usually its CRDs. hello-world is one of them: its
`HTTPRoute` needs the Gateway API CRDs, which the `gateway-api-crds` release installs. That release is one of those
the bundle of the [envoy-gateway](/bases/stacks/envoy-gateway/) stack creates. You tell Flux with `dependsOn` on the `HelmRelease`.
helm-controller checks it on every reconciliation, so every install and upgrade waits until the other release is
`Ready`. The install retries can stay bounded, so a broken install still fails rather than retrying forever.

The catch is that a `HelmRelease` named in `dependsOn` has to exist, or the release waits forever. So a template that
should work on its own leaves the dependency out, and the layer that installs both releases adds it. hello-world's
template leaves it out, and the [hello-web](/bases/stacks/hello-web/) stack, which installs it with envoy-gateway, adds
it with a patch:

```yaml
patches:
  - patch: |-
      - op: add
        path: /spec/dependsOn
        value:
          - name: ${cluster_name}-gateway-api-crds
    target:
      kind: HelmRelease
      name: \${cluster_name}-hello-world
```

A cluster that installs envoy-gateway itself adds the same patch to its own hello-world directory, as yours does
since [Deploy it to a cluster](#deploy-it-to-a-cluster), and as
[apps/hello-world-from-template](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world-from-template/kustomization.yaml)
in the `out-of-band-no-flux` example does.

`dependsOn` orders installs and upgrades, not deletes. When several `HelmRelease`s are deleted at once, such as a
stack's when a `Kustomization` prunes it, helm-controller uninstalls them all together, in no order you chose. A chart
that minds has to say so itself. The bundle of the envoy-gateway stack does: before its `HelmRelease`s go, a
`pre-delete` hook uninstalls `gateway-api-config` while Envoy Gateway is still there to clear the finalizer of the
`giantswarm-default` `GatewayClass`. The [stack's README](/bases/stacks/envoy-gateway/README.md) has the timeout that
goes with it.

## Next steps

- [Stacks](./stacks.md): tie hello-world and Envoy Gateway together, so a cluster gets both from one line.
- [Automatic updates](./automatic-updates.md): let Flux move a template's version for you.
- [Add an app](../../how-to/add-app.md): the short version of adding an app, directly or from a template.
