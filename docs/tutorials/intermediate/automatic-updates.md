# Automatic updates

In the [basic tutorial](../basic/getting-started.md#5-update-the-app) you updated hello-world by changing its version
in Git and pushing. Every new chart version is a pull request, which is what you want for an app you have to watch
closely, and a chore for one you don't. For those, let Flux install new versions by itself.

The chart version of an app is set in its `OCIRepository`. Instead of a fixed `spec.ref.tag`, give it a
`spec.ref.semver` range: Flux then picks the highest chart tag that satisfies the range, checks the registry again
every `spec.interval`, and the `HelmRelease` upgrades the app as soon as a newer matching tag shows up. No other Flux
objects are needed, and Flux doesn't commit anything to the repository: the repository keeps the range, and the
cluster reports the version it installed.

A range upgrades the app whenever a new version is published, at any time of day. To hold upgrades back until an
upgrade window instead, see [Scheduled upgrades](../advanced/scheduled-upgrades.md).

- [Set a version range](#set-a-version-range)
- [Apps from an App Template or a stack](#apps-from-an-app-template-or-a-stack)
- [Check the installed version](#check-the-installed-version)
- [Next steps](#next-steps)

Run the commands from the root of your clone, with the variables the basic tutorial exported still set: those from
[Before you start](../basic/getting-started.md#before-you-start), and the ones its steps add, such as `WC_CONTEXT`.
The fork has a finished example in
[WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-automatic-updates](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-automatic-updates/oci-repository.yaml).

## Set a version range

A range goes on an app with an `oci-repository.yaml` of its own. If you followed [App Templates](./app-templates.md)
and [Stacks](./stacks.md), your cluster's hello-world gets its `OCIRepository` from the stack now, so add a small app
of its own to try the range on: hello-world once more, as `hello-world-auto`, in a namespace of its own.

1. Create the app with a fixed version, as in the basic tutorial. `3.2.2` is the oldest hello-world that takes the
   cluster values: earlier versions have a values schema that refuses them. Starting there leaves the range something
   to do. Its Ingress is switched off, as in the basic tutorial, so that it doesn't claim the host of the cluster's
   other hello-world:

    ```sh
    export APP_DIR=${WC_DIR}/apps/hello-world-auto
    mkdir -p ${APP_DIR}
    cat <<'EOF' > ${APP_DIR}/oci-repository.yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}-hello-world-auto
      namespace: org-${organization}
    spec:
      interval: 10m
      ref:
        tag: 3.2.2
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
    EOF
    cat <<'EOF' > ${APP_DIR}/helm-release.yaml
    apiVersion: helm.toolkit.fluxcd.io/v2
    kind: HelmRelease
    metadata:
      name: ${cluster_name}-hello-world-auto
      namespace: org-${organization}
    spec:
      chartRef:
        kind: OCIRepository
        name: ${cluster_name}-hello-world-auto
      install:
        createNamespace: true
      interval: 5m
      kubeConfig:
        secretRef:
          name: ${cluster_name}-kubeconfig
      releaseName: hello-world-auto
      storageNamespace: hello-world-auto
      targetNamespace: hello-world-auto
      values:
        ingress:
          enabled: false
      valuesFrom:
        - kind: ConfigMap
          name: ${cluster_name}-cluster-values
          valuesKey: values
    EOF
    cat <<'EOF' > ${APP_DIR}/kustomization.yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    namespace: org-${organization}
    resources:
      - oci-repository.yaml
      - helm-release.yaml
    EOF
    yq -i '.resources += ["hello-world-auto"]' ${WC_DIR}/apps/kustomization.yaml
    ```

1. Replace the fixed version with a range: here, every release from `3.2.2` on, but below the next major version,
   which might bring breaking changes:

    ```sh
    yq -i '.spec.ref = {"semver": ">=3.2.2 <4.0.0"}' ${APP_DIR}/oci-repository.yaml
    ```

    > **Shortcut:** [`kubectl gs gitops add automatic-update`](https://docs.giantswarm.io/reference/kubectl-gs/gitops/add-update/)
    > makes the same change, and only that one, to the app's `oci-repository.yaml`. It needs kubectl-gs 6.0.0 or newer,
    > see [kubectl-gs version](../../reference/tools.md#kubectl-gs-version). Run it from the repository root, with
    > `--skip-mapi`: without it, kubectl-gs looks for the app under a `mapi` directory, which this repository doesn't
    > have:
    >
    > ```sh
    > kubectl gs gitops add automatic-update --management-cluster ${MC_NAME} --organization ${ORG_NAME} \
    >   --workload-cluster ${WC_NAME} --app hello-world-auto --version-range '>=3.2.2 <4.0.0' --skip-mapi
    > ```
    >
    > The `--workload-cluster` is the name of the cluster's directory, and `--app` the name of the app's. Nothing
    > needs fixing afterwards. It refuses an app made from an App Template, whose `OCIRepository` is in the template:
    > for those, see the next section.

    The file now looks like this:

    ```yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}-hello-world-auto
      namespace: org-${organization}
    spec:
      interval: 10m
      ref:
        semver: '>=3.2.2 <4.0.0'
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
    ```

1. Commit and push:

    ```sh
    git add ${WC_DIR}/apps && git commit -m "Update hello-world-auto on ${WC_NAME} automatically" && git push
    ```

A range only matches pre-release tags, the ones with a `-` after the version, if it has a pre-release comparator
itself, such as `>=3.2.2-0`. Don't reach for one to get releases sooner. On `gsoci.azurecr.io` a pre-release isn't a
release candidate: it's a build of a branch that hasn't been merged, and semver sorts those by a hash of the branch
name, so "the newest pre-release" is whichever branch hash sorts last, not the latest build. The
[dev stage](./stages-and-regions.md#stages) is where pre-releases belong, with `spec.ref.semverFilter` to say which
ones. The [OCIRepository docs](https://fluxcd.io/flux/components/source/ocirepositories/) have all the options.

## Apps from an App Template or a stack

The `OCIRepository` of an app made from an [App Template](./app-templates.md) is part of the template, so there's no
file of the cluster's to change. Patch it in the app's `kustomization.yaml` instead, for this cluster only. After
[Stacks](./stacks.md), that's `${WC_DIR}/apps/hello-web/kustomization.yaml`; if it already has a version patch for
hello-world from App Templates, replace that one with this:

```yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref
        value:
          semver: '>=3.2.2 <4.0.0'
    target:
      kind: OCIRepository
      name: \${cluster_name}-hello-world
```

kustomize applies the cluster's patches after the template's own, so the range replaces the version the template pins.
The `$` of the target name is escaped, as kustomize reads the name as a regular expression.

The same patch works for an app of a [stack](./stacks.md), but think before you use it there. A stack usually pins
its versions on purpose, because its apps are known to work together at those versions, and a range lets one of them
wander off on its own.

To give every cluster that uses a template the range, set it in the template's own `oci-repository.yaml` instead.

## Check the installed version

The repository only holds the range. To see which version Flux picked, look at the `OCIRepository`, whose artifact is
the chart version, and at the `HelmRelease` on the management cluster:

```sh
flux get sources oci -n org-${ORG_NAME}
flux get helmreleases -n org-${ORG_NAME}
```

## Next steps

- [Scheduled upgrades](../advanced/scheduled-upgrades.md): new versions, but only inside an upgrade window.
- [Pull the chart from a private registry](../../how-to/add-app.md#pull-the-chart-from-a-private-registry): give the
  `OCIRepository` credentials for a registry that isn't public.
- [Stages and regions](./stages-and-regions.md): a range in dev, pins in staging and prod.
