# Enable automatic updates of an existing App

- [Enable automatic updates of an existing App](#enable-automatic-updates-of-an-existing-app)
  - [Example](#example)
  - [Export environment variables](#export-environment-variables)
  - [Version range](#version-range)
  - [Apps created from an App Template](#apps-created-from-an-app-template)
  - [Apps from an App Set](#apps-from-an-app-set)
  - [Checking the installed version](#checking-the-installed-version)
  - [Credentials for private registries (optional)](#credentials-for-private-registries-optional)
  - [Upgrade windows with Flux Operator](#upgrade-windows-with-flux-operator)
    - [When to use it](#when-to-use-it)
    - [How the examples work](#how-the-examples-work)
    - [Installing before the first window](#installing-before-the-first-window)
    - [Moving an existing cluster](#moving-an-existing-cluster)
    - [Notes on the examples](#notes-on-the-examples)
    - [What the window does](#what-the-window-does)
    - [Losing the version](#losing-the-version)

Follow the below instructions to tell Flux to automatically update an existing App. Automatic update means
that Flux will check the chart registry for you and automatically install new chart versions as they are published.

The chart version of an App is set in its `OCIRepository`. Instead of a fixed `spec.ref.tag`, you can give it a
`spec.ref.semver` range: Flux then picks the highest chart tag that satisfies the range, checks the registry again
every `spec.interval`, and the `HelmRelease` upgrades the App as soon as a newer matching tag shows up. No other Flux
objects are needed, and Flux doesn't commit anything to this repository: the repository keeps the range, the cluster
reports the version it installed.

## Example

An example of an App with automated updates is available in
[WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-automatic-updates](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/apps/hello-world-automatic-updates/oci-repository.yaml).

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and App name are needed in
multiple places across this instruction, the least error prone way of providing them is by exporting as environment
variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
```

## Version range

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
    ```

1. Replace the fixed version of the `OCIRepository` with a version range, for example every release from `3.0.0` on,
   but below the next major version, which might bring breaking changes:

    ```sh
    yq -i '.spec.ref = {"semver": ">=3.0.0 <4.0.0"}' oci-repository.yaml
    ```

    `kubectl gs gitops add automatic-update` makes the same change. It needs kubectl-gs 6.0.0 or newer, see
    [kubectl-gs version](../appendices.md#kubectl-gs-version). Run it from the repository root:

    ```sh
    kubectl gs gitops add automatic-update --management-cluster ${MC_NAME} --organization ${ORG_NAME} \
      --workload-cluster ${WC_NAME} --app ${APP_NAME} --version-range '>=3.0.0 <4.0.0'
    ```

    It needs the App's `OCIRepository` in `oci-repository.yaml` in the App directory, so it doesn't work for Apps
    created from an App Template, see below.

    The resulting file should look similar to this:

    ```yaml
    apiVersion: source.toolkit.fluxcd.io/v1
    kind: OCIRepository
    metadata:
      name: ${cluster_name}-hello-world
      namespace: org-${organization}
    spec:
      interval: 10m
      provider: generic
      ref:
        semver: '>=3.0.0 <4.0.0'
      url: oci://gsoci.azurecr.io/charts/giantswarm/hello-world
    ```

    **Note**, a range only matches pre-release tags, like `3.1.0-rc.1`, if it has a pre-release comparator itself:
    `>=3.0.0-0` matches every release and pre-release from `3.0.0` on. Use `spec.ref.semverFilter` to narrow the
    matching tags down with a regular expression, see
    [Add Workload Cluster environments](./environments.md#the-development-cluster) for an example that
    follows development builds, and the [OCIRepository docs](https://fluxcd.io/flux/components/source/ocirepositories/)
    for all the options.

## Apps created from an App Template

The `OCIRepository` of an App created from an [App Template](./app-templates.md) is part of the Template. To enable
automatic updates for a single cluster, add a patch to the App's `kustomization.yaml` instead. The `$` of the target
name is escaped, as `kustomize` reads the name as a regular expression:

```yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref
        value:
          semver: '>=3.0.0 <4.0.0'
    target:
      kind: OCIRepository
      name: \${cluster_name}-hello-world
```

## Apps from an App Set

For an App installed through an [App Set](./app-sets.md), add the same patch to the `kustomization.yaml` of the App Set
instance, in the cluster's `app_sets/YOUR_APP_SET` directory. Kustomize applies the instance's patches after the
App Set Template's, so the range replaces the version the App Set pins, for this cluster only. Bear in mind that an
App Set usually pins its versions on purpose, because its apps are known to work well together at those versions.

## Checking the installed version

The repository only holds the range. To see which version Flux picked, check the `OCIRepository` and `HelmRelease` on
the Management Cluster:

```sh
kubectl get ocirepositories,helmreleases -n org-${ORG_NAME}
```

## Credentials for private registries (optional)

Charts from the Giant Swarm catalog are public. If your chart is in a private registry, give the `OCIRepository`
credentials to read it.

1. Export path to the Docker registry config with credentials:

    ```sh
    export DOCKER_CONFIG_JSON=PATH
    ```

1. Go to the App directory:

    ```sh
    cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
    ```

1. Create Kubernetes Secret with Docker Registry credentials in the organization namespace, where the `OCIRepository`
   lives, and save it into a file:

    ```sh
    kubectl create secret docker-registry \
    ${WC_NAME}-${APP_NAME}-pull-secret \
    --namespace org-${ORG_NAME} \
    --from-file .dockerconfigjson=${DOCKER_CONFIG_JSON} \
    --dry-run=client \
    -o yaml > pullsecret.enc.yaml
    ```

1. Import the Workload Cluster's GPG public key and encrypt the Kubernetes Secret with it. The SOPS rule for the
   cluster picks the key; if the cluster has none in `.sops.yaml` yet, add its key and rule with
   [the WC structure guide](../add_wc_structure.md#create-flux-gpg-regular-key-pair-optional-step) first:

    ```sh
    gpg --import "$(git rev-parse --show-toplevel)/management-clusters/${MC_NAME}/.sops.keys/.sops.${WC_NAME}.asc"
    sops --encrypt --in-place pullsecret.enc.yaml
    ```

1. Reference the Secret in the `OCIRepository`:

    ```sh
    yq -i ".spec.secretRef.name = \"${WC_NAME}-${APP_NAME}-pull-secret\"" oci-repository.yaml
    ```

1. Add the Secret to the resources of the App's `kustomization.yaml`:

    ```sh
    yq -i '.resources += ["pullsecret.enc.yaml"]' kustomization.yaml
    ```

## Upgrade windows with Flux Operator

A version range upgrades the App as soon as a new version is published, at any time of day. Flux Operator, which runs
on every Giant Swarm management cluster, can hold upgrades back until an upgrade window instead. Its API,
`fluxcd.controlplane.io/v1`, is used as it is:

- a `ResourceSetInputProvider` of type `OCIArtifactTag` lists the tags of the chart, keeps the ones in its
  `spec.filter.semver` range and exports the highest. Its `spec.schedule` decides when it looks.
- a `ResourceSet` renders the App's `OCIRepository` and `HelmRelease` from that version, with
  `<< inputs.tag >>` where the version goes.

### When to use it

A plain `HelmRelease` is enough when:

- a pinned version is fine: every upgrade is a pull request, and it reaches the cluster when it's merged.
- a range is fine: the App may upgrade whenever a new version is published.

Use a `ResourceSetInputProvider` and a `ResourceSet` when upgrades have to wait for a window, for example the release
of a production cluster, or an App that should only restart in working hours. A `ResourceSet` also rolls the same App
out to several workload clusters from one list.

### How the examples work

- [resource-sets/hello-world-scheduled](/management-clusters/MC_NAME/organizations/ORG_NAME/resource-sets/hello-world-scheduled/resource-set.yaml)
  installs hello-world on two workload clusters, which its `ResourceSet` lists in `spec.inputs`. Its provider picks the
  highest release below `4.0.0` from Monday to Thursday, 09:00 to 17:00 in Berlin. With `inputStrategy: Permute`, the
  `ResourceSet` renders an `OCIRepository` and a `HelmRelease` for every cluster at that version. Removing a cluster
  from `spec.inputs` uninstalls the App from that cluster.
- [WC_NAME_SCHEDULED_UPGRADES](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_SCHEDULED_UPGRADES/cluster/cluster-resource-set.yaml)
  is a cluster whose Giant Swarm release moves to the highest `v36` release only on Tuesdays, 02:00 to 05:00 UTC. Its
  `ResourceSet` renders the whole cluster, the `OCIRepository` and the `HelmRelease` as the cluster base has them, at
  the version its provider picks; a patch drops the base's two. The base and the region component still give the
  cluster its values, and the `HelmRelease` lists the region's values itself, as a component's patch doesn't reach into
  a `ResourceSet`. A new major release is a change to the range in Git, and an exact version in the range pins the
  cluster to it. Like a new release, a change to the range reaches the cluster at the next window, or at once when you
  force the provider, see below.

### Installing before the first window

A new provider whose window is closed reports `Ready` but exports no version until the window opens. Until then its
`ResourceSet` waits, so the App isn't installed and the cluster isn't created. To install at once, force the provider
once, after Flux has applied it. It then reads the registry outside its schedule, this one time:

```sh
# the hello-world example
flux-operator reconcile inputprovider hello-world-scheduled-version -n org-${ORG_NAME} --force
# the WC_NAME_SCHEDULED_UPGRADES example: its provider is named after the cluster
flux-operator reconcile inputprovider ${CLUSTER_NAME}-release -n org-${ORG_NAME} --force
```

Without the `flux-operator` CLI, set both annotations to the same new value:

```sh
now="$(date +%s)"
kubectl annotate resourcesetinputprovider ${CLUSTER_NAME}-release -n org-${ORG_NAME} --overwrite \
  reconcile.fluxcd.io/requestedAt="${now}" reconcile.fluxcd.io/forceAt="${now}"
```

Later upgrades still wait for the window. The comments in both examples' providers and `ResourceSet`s give the same
step, and the kind test does the same for both examples.

### Moving an existing cluster

A cluster that the cluster base creates can move to the layout of `WC_NAME_SCHEDULED_UPGRADES`. Its `OCIRepository` and
`HelmRelease` leave its `Kustomization`, which doesn't delete them, as both have the
`kustomize.toolkit.fluxcd.io/prune: disabled` annotation, and its `ResourceSet` takes them over once its provider has a
version. Forcing the provider picks the highest release in the range at once, outside the window, so pin the range to
the release the cluster runs first:

1. Wait until Flux has applied the updated cluster base, so that the cluster's live `OCIRepository` has the
   `kustomize.toolkit.fluxcd.io/prune: disabled` annotation. Without it, the move tries to prune the `OCIRepository`,
   which the `giantswarm.io/prevent-deletion` label refuses, and the prune fails.
1. Set the provider's `spec.filter.semver` to the cluster's current release, the `release` in its `Kustomization`, for
   example `'36.2.0'`. Move the cluster's files to the example's layout, then commit and push.
1. Once Flux has applied the provider, force it as above. The `ResourceSet` takes over the `OCIRepository` and the
   `HelmRelease` at the release the cluster already runs, so the cluster doesn't change.
1. Set the range back, for example to `'>=36.0.0 <37.0.0'`, then commit and push. The cluster moves to the highest
   release in it at the next window.

### Notes on the examples

Keep one `ResourceSet` per App, as the example does: a `ResourceSet` deletes what it rendered for an input that has
gone, so Apps that shared one would go together. Set `spec.filter.limit: 1`, or every exported tag becomes a release
of its own. The `ResourceSet`s run as the organization's `automation` service account, in `spec.serviceAccountName`:
Flux Operator applies what they render with that account's permissions, and a Kyverno policy on the management
clusters rejects a `ResourceSet` without one. The `ResourceSet` and its provider have to be in the same namespace.

To see which version a provider picked, and when it looks next:

```sh
kubectl get resourcesetinputproviders -n org-${ORG_NAME} \
  -o 'custom-columns=NAME:.metadata.name,VERSION:.status.exportedInputs[0].tag,NEXT:.status.nextSchedule.when'
```

### What the window does

The kind test checks what follows, in `tests/ats/resource_set_schedule.py`.

With a `window`, the provider looks at the registry only while the window is open: from the `cron` time, in its
`timeZone`, for the length of the window, less the provider's timeout of two minutes. Inside the window it looks every
10 minutes. Outside it, nothing moves the version: not a new release, and not a change to the range in Git either.
Both wait for the next window. A window has to be at least twice the timeout, so at least `4m`.

`window` defaults to `0s`, which Flux Operator's API documents as "no window is applied". That doesn't turn the
schedule off, and it doesn't hold upgrades back either: the provider looks at the `cron` time, and also whenever
something asks it to, such as a change to its spec or a restart of Flux Operator. It only stops looking every 10
minutes. Set a `window` to keep upgrades in the window.

### Losing the version

Without a version, a `ResourceSet` renders nothing and deletes what it rendered before, which uninstalls the App or
deletes the cluster. The version goes when no tag matches the range, when the registry can't be read or when the
provider is deleted. Both examples guard against it with a `dependsOn` on their provider:

```yaml
dependsOn:
  - apiVersion: fluxcd.controlplane.io/v1
    kind: ResourceSetInputProvider
    name: hello-world-scheduled-version
    namespace: org-org-name
    ready: true
    readyExpr: >-
      status.conditions.exists(c, c.type == 'Ready' && c.status == 'True')
      && has(status.exportedInputs)
```

Until the provider is `Ready` with a version, the `ResourceSet` reports `DependencyNotReady` and leaves what it
rendered as it is. The cluster's `OCIRepository` and `HelmRelease` also have the `fluxcd.controlplane.io/prune:
disabled` annotation, so the `ResourceSet` never deletes them, not even when the `ResourceSet` itself is deleted or its
file is deleted from Git, and the `giantswarm.io/prevent-deletion` label, as in the cluster base. The kind test takes
the version away in each of the three ways and checks that the App stays installed, in
`tests/ats/resource_set_guard.py`, and that the cluster's `HelmRelease` and `OCIRepository` stay, also when the
`ResourceSet` is deleted, in `tests/ats/resource_set_cluster_guard.py`.
