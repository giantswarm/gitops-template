# Add Workload Cluster environments

- [General note](#general-note)
- [Environments](#environments)
  - [Stages](#stages)
    - [The development cluster](#the-development-cluster)
    - [The staging cluster](#the-staging-cluster)
    - [The production cluster](#the-production-cluster)
    - [Promote a change from dev to prod](#promote-a-change-from-dev-to-prod)
- [Add Workload Clusters based on the environment cluster templates](#add-workload-clusters-based-on-the-environment-cluster-templates)
- [Tips for developing environments](#tips-for-developing-environments)

You might want to set up multiple, similar Workload Clusters that serve as for example development,
staging and production environments. You can utilize [bases](/bases) to achieve that. Let's take a look at the
[/bases/environments](/bases/environments) folder structure.

## General note

It is possible to solve the environment and environment propagation problem in multiple ways, notably by:

- using a multi-directory structure, where each environment is represented as a directory in a `main` branch of a single
  repository
- using a multi-branch approach, where each branch corresponds to one environment, but they are in the same repo
- using a multi-repo setup, where there's one root repository providing all the necessary templates, then there is one another
  repository per environment.

Each of these approaches has pros and cons. We propose the multi-directory approach. The pros of it are:
a single repo and branch serving as the source of truth for all the environments, very easy template sharing and
relatively easy way to compare and promote configuration across environments. On the other hand, it might not be the
best solution for access control, template versioning and also easy comparing of environments.

## Environments

The `stages` folder is how we propose to group environment specifications.
There is a good reason for this additional layer of grouping. You can use this approach to have multiple
different clusters - like the dev, staging, production - but also to have multiple different
regions where you want to spin these clusters up.

```sh
mkdir -p bases/environments/stages
```

We're assuming that all the clusters using this environments pattern should in many regards look the same
across all the environments. Still, each environment layer introduces some key differences, like app version being deployed
for `dev/staging/prod` environments or a specific IP range, availability zones, certificates or ingresses config
for regions like `eu-central/us-west`.

To create an environment template, you need to make a  directory in `environments` that describes the best the
differentiating factor for that kind of environment, then you should create sub folder there for different possible values.
For example, for multiple regions, we recommend putting region specific configuration into
`/bases/environments/regions` folder and under there create e.g. `eu_central`, `us_west` folders.

Once your environment templates are ready, you can use them to create new clusters by placing cluster definitions
in [/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters)

### Stages

We have 3 example clusters under [/bases/environments/stages](/bases/environments/stages):

- [dev](/bases/environments/stages/dev)
- [staging](/bases/environments/stages/staging)
- [prod](/bases/environments/stages/prod)

```sh
mkdir -p bases/environments/stages/dev
mkdir -p bases/environments/stages/staging
mkdir -p bases/environments/stages/prod
```

Each of these contain a `hello_app_cluster` example, built from the
[hello_app_cluster](/bases/cluster_templates/hello_app_cluster) cluster template that ships with this repository. A
cluster template bundles everything a kind of cluster gets: here the [CAPA cluster base](/bases/clusters/capa/template),
the [envoy-gateway](/bases/apps/envoy-gateway) App Template and the [hello-web-app](/bases/app_sets/hello-web-app) App
Set, with the per-cluster values that tie them together. None of the other docs create it, so if your repository doesn't
have it, copy `bases/cluster_templates/hello_app_cluster` together with the bases it references.

The cluster template also orders hello-world after the Gateway API CRDs: a patch in its `kustomization.yaml` adds
`${cluster_name}-gateway-api-crds` to the hello-world `HelmRelease`'s `dependsOn`, so every install and upgrade of
hello-world waits until that envoy-gateway release is `Ready`. When you compose your own cluster template from these
App Templates, add the same patch; see [App Templates](./app-templates.md).

```sh
mkdir -p bases/environments/stages/dev/hello_app_cluster
mkdir -p bases/environments/stages/staging/hello_app_cluster
mkdir -p bases/environments/stages/prod/hello_app_cluster
```

By checking each `kustomization.yaml` files - the [dev](
/bases/environments/stages/dev/hello_app_cluster/kustomization.yaml) one for example - you will notice that they
all reference our [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
# ...
resources:
  # ...
  - ../../../../cluster_templates/hello_app_cluster
```

You can put additional configuration under these folders that should be same for each instances of these clusters.
Let's take a closer look at our examples.

#### The development cluster

Set up our environment first.

```sh
export MC_NAME=CODENAME
export WC_NAME=CLUSTER_NAME
export ORG_NAME=ORGANIZATION
export GIT_REPOSITORY_NAME=REPOSITORY_NAME
```

Each stage also pins the Giant Swarm release its clusters run. The cluster template uses the CAPA cluster base, whose
`release-aws` chart has the release as its version, so a patch sets the release as the tag of the cluster's
`OCIRepository`.
Pick an AWS release from v34.0.0 on, which has a `release-aws` chart. Each stage pins its own release, so a new release
reaches dev first and staging and prod only when you promote it, see
[Promote a change from dev to prod](#promote-a-change-from-dev-to-prod). In this example dev runs `36.2.0`, staging
`36.1.1` and prod `36.1.0`.

```sh
export RELEASE_VERSION=36.2.0
```

Change our working directory to the `hello_app_cluster` development cluster environment base.

```sh
cd bases/environments/stages/dev/hello_app_cluster
```

The [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) base cluster template defines that the
[hello-web-app app set](/bases/app_sets/hello-web-app) should be installed in all of these clusters. Values for the
apps in that set come from the set itself, through [override_config_hello_world.yaml](
/bases/cluster_templates/hello_app_cluster/app_sets/hello-web-app/override_config_hello_world.yaml) in the cluster
template; what a stage adds on top is the chart version to run.

The version of an app lives on its `OCIRepository`, and it can be either a fixed `spec.ref.tag` or a `spec.ref.semver`
range. With a range, Flux deploys the highest chart tag that satisfies it and upgrades the app as soon as a newer
matching tag is published, so `Automatic Updates` need nothing besides the `OCIRepository` itself. See the
[OCIRepository docs](https://fluxcd.io/flux/components/source/ocirepositories/) for `semver` and
`semverFilter`.

For our development cluster we want Flux to automatically roll out the dev builds of `hello-world` from version
`3.0.0` on. Dev builds are pre-releases tagged `X.Y.Z-r<branch-CRC32>t<timestamp>h<sha>`. The `-0` suffix on the range
makes pre-releases eligible at all, `semverFilter` then keeps only dev builds. Flux picks the highest matching tag, and
for builds of the same version semver orders by the branch hash before the timestamp, so if several branches publish dev
builds, put the CRC32 of the branch to follow into the filter instead of `[0-9a-f]{8}`.

Let's create the `kustomization.yaml` file for the development cluster. A patch sets the release as the tag of the
cluster's `OCIRepository`. Don't set `global.release.version` in the cluster values, because the `release-aws` chart
sets it.

```sh
cat <<EOF > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
patches:
  - patch: |-
      - op: replace
        path: /spec/ref
        value:
          semver: '>=3.0.0-0'
          semverFilter: '-r[0-9a-f]{8}t[0-9]{14}h[0-9a-f]{7}'
    target:
      kind: OCIRepository
      name: \\\${cluster_name}-hello-world
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
        value: "${RELEASE_VERSION}"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

The `# renovate:` comment lets Renovate find the release, which it can't see in a kustomize patch otherwise.

And pretty much that is it for the development cluster. Let's look at the staging cluster next to the minor differences.

#### The staging cluster

Let's change our working directory to the staging cluster.

```sh
cd ../../staging/hello_app_cluster
```

We will use the same environment variables for this cluster template as we did for the development cluster.

It is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base, like the development
cluster. Unlike it, staging doesn't follow a range: it pins the exact `hello-world` version and the release, so it only
runs a version once you have promoted it from dev. The hello-world patch overrides the version the app set pins.

```sh
cat <<EOF > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
patches:
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
        value: "3.2.4"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}-hello-world
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
        value: "36.1.1"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

So basically our staging cluster in our example is a smaller scale cluster carrying stable versions of our applications.

Now, let's take a look at the production cluster example.

#### The production cluster

Let's change our working directory to the production cluster.

```sh
cd ../../prod/hello_app_cluster
```

We will use the same environment variables for this cluster template as we did for the development cluster.

Let's create the `Kustomization` for the production cluster environment template.

```sh
cat <<EOF > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
configMapGenerator:
  - behavior: replace
    files:
      - values=cluster_userconfig.yaml
    name: \${cluster_name}-cluster-userconfig
    namespace: org-\${organization}
generatorOptions:
  disableNameSuffixHash: true
  labels:
    reconcile.fluxcd.io/watch: Enabled
kind: Kustomization
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

It is similar to the staging cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base
- it pins the exact versions it runs instead of following a range

Note in the `kustomization.yaml` above that we replace the empty `${cluster_name}-cluster-userconfig` `ConfigMap` of the
cluster template with extra settings for the production cluster: bigger nodes, and more of them.

```sh
cat <<EOF > cluster_userconfig.yaml
global:
  nodePools:
    nodepool0:
      instanceType: m6a.8xlarge
      maxSize: 50
      minSize: 10
EOF
```

Like staging, we use the `Kustomization` in the cluster's [kustomization.yaml](
/bases/environments/stages/prod/hello_app_cluster/kustomization.yaml) to patch the exact versions to use
in our `OCIRepository` resources, next to the release of the cluster.

```sh
cat <<EOF >> kustomization.yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/hello-world versioning=docker
        value: "3.2.2"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}-hello-world
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        # renovate: datasource=docker depName=gsoci.azurecr.io/charts/giantswarm/release-aws versioning=docker
        value: "36.1.0"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}
EOF
```

We tell Flux to use version `3.2.2` of the `hello-world` app and release `36.1.0`, one step behind staging.

#### Promote a change from dev to prod

Every stage runs its own version, and a version moves from one stage to the next in a pull request:

| Stage | hello-world | Release |
| --- | --- | --- |
| dev | the newest dev build, from a `semver` range | `36.2.0` |
| staging | `3.2.4` | `36.1.1` |
| prod | `3.2.2` | `36.1.0` |

[Renovate](/renovate.json5) finds the pins by their `# renovate:` comments, and opens a pull request per stage for each
new version of hello-world and of the release:

- **dev**: hello-world follows its range, so Flux deploys a new dev build without a pull request. A new release comes
  in the pull request without a stage prefix, which also updates the bases and the `WC_NAME*` example clusters.
- **staging**: a pull request on a `renovate/staging-*` branch changes the staging stage and the kind test's
  assertions for the staging clusters.
- **prod**: a pull request on a `renovate/prod-*` branch does the same for the prod stage.

The staging and prod pull requests, and every pull request that changes a release, are never automerged: a release
update rolls the cluster's nodes. Merging them in order is the promotion:

1. dev gets the change first. Flux deploys each dev build of hello-world as it is published; for a release, merge the
   dev pull request.
1. Once the change works in dev, and for hello-world is published as a stable version, merge the staging pull request.
1. Once it works in staging, merge the prod pull request.

Without Renovate, promote the same way: change the version in the next stage's `kustomization.yaml` and merge it. To
promote a version other than the newest, change the version in Renovate's pull request before you merge it.

#### Regions

Every cluster runs in a region, and every cluster has to say which. Without `global.providerSpecific.region`, the
`release-aws` chart takes the region of the management cluster's nodes, so a cluster would quietly be created in the
region of its management cluster. `tools/validate-helm-values` fails for a cluster without a region.

A region is a [kustomize Component](https://kubectl.docs.kubernetes.io/guides/config_management/components/) in
`bases/environments/regions`. It creates the `${cluster_name}-region-config` ConfigMap with the region and appends it to
the cluster's `HelmRelease` `valuesFrom`. A region can also have an extra node pool in its zones, in a second component
that the clusters which need it add, like the production clusters here.

Relative to root of the repository let's execute the following commands.

```bash
mkdir -p bases/environments/regions/eu_central/node_pool
mkdir -p bases/environments/regions/us_west/node_pool

cd bases/environments/regions
```

For the `eu-central` region.

```bash
cat <<EOF > eu_central/region_config.yaml
global:
  providerSpecific:
    region: eu-central-1
EOF

cat <<EOF > eu_central/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
configMapGenerator:
  - files:
      - values=region_config.yaml
    name: \${cluster_name}-region-config
    namespace: org-\${organization}
generatorOptions:
  disableNameSuffixHash: true
  labels:
    reconcile.fluxcd.io/watch: Enabled
patches:
  - patch: |-
      - op: add
        path: /spec/valuesFrom/-
        value:
          kind: ConfigMap
          name: \${cluster_name}-region-config
          valuesKey: values
    target:
      group: helm.toolkit.fluxcd.io
      kind: HelmRelease
      name: \\\${cluster_name}
EOF
```

Its extra node pool spans the region's zones.

```bash
cat <<EOF > eu_central/node_pool/node_pool.yaml
global:
  nodePools:
    large:
      availabilityZones:
        - eu-central-1a
        - eu-central-1b
        - eu-central-1c
      instanceType: m6a.2xlarge
      maxSize: 10
      minSize: 1
EOF

cat <<EOF > eu_central/node_pool/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1alpha1
kind: Component
configMapGenerator:
  - files:
      - values=node_pool.yaml
    name: \${cluster_name}-region-node-pool-config
    namespace: org-\${organization}
generatorOptions:
  disableNameSuffixHash: true
  labels:
    reconcile.fluxcd.io/watch: Enabled
patches:
  - patch: |-
      - op: add
        path: /spec/valuesFrom/-
        value:
          kind: ConfigMap
          name: \${cluster_name}-region-node-pool-config
          valuesKey: values
    target:
      group: helm.toolkit.fluxcd.io
      kind: HelmRelease
      name: \\\${cluster_name}
EOF
```

For the `us-west` region, the two `kustomization.yaml` files are the same as for `eu-central`. Only the values differ:
the region is `us-west-2`, the pool's zones are `us-west-2a`, `us-west-2b` and `us-west-2c`, and the pool uses the
larger `m6a.4xlarge` instances instead of `m6a.2xlarge`.

```bash
cp eu_central/kustomization.yaml us_west/kustomization.yaml
cp eu_central/node_pool/kustomization.yaml us_west/node_pool/kustomization.yaml

cat <<EOF > us_west/region_config.yaml
global:
  providerSpecific:
    region: us-west-2
EOF

cat <<EOF > us_west/node_pool/node_pool.yaml
global:
  nodePools:
    large:
      availabilityZones:
        - us-west-2a
        - us-west-2b
        - us-west-2c
      instanceType: m6a.4xlarge
      maxSize: 10
      minSize: 1
EOF
```

The pool is called `large` and doesn't share a key with the stage's `nodepool0`, so a production cluster gets both
pools: the stage's and the region's. The dev and staging clusters don't add the node pool component, so they only get
the chart's default node pools.

## Add Workload Clusters based on the environment cluster templates

Just as any other Workload Clusters we define them in
[/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters).

Relative to the root of the repository, let's change our working directory to our `workload-clusters` folder.

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
```

Then let's tell Flux to manage our cluster instance. It doesn't set `organization`: the organisation's
`kustomization.yaml` sets it from the name of the `Organization`, see
[The organisation's name](../reference/repo-structure.md#the-organisations-name).

```sh
cat <<EOF > HELLO_APP_DEV_CLUSTER_1.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: ${MC_NAME}-clusters-hello-app-dev-1
  namespace: default
spec:
  interval: 10m
  path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/HELLO_APP_DEV_CLUSTER_1"
  postBuild:
    substitute:
      cluster_description: "description"
      cluster_name: "hello-app-dev-1"  # must be a valid Kubernetes name
  prune: true
  retryInterval: 1m
  serviceAccountName: automation
  sourceRef:
    kind: GitRepository
    name: ${GIT_REPOSITORY_NAME}
  timeout: 2m
EOF
```

Then add it to the `kustomization.yaml` of the `workload-clusters` directory, so Flux creates it:

```sh
yq -i eval ".resources += \"HELLO_APP_DEV_CLUSTER_1.yaml\" | .resources style=\"\"" kustomization.yaml
```

> **Note**
>
> With `prune: true`, Flux deletes what you delete from the cluster's files, and
> everything the `Kustomization` applied when the `Kustomization` itself goes. It
> doesn't delete the cluster: the cluster's `HelmRelease`, from the CAPA cluster
> base, has the `kustomize.toolkit.fluxcd.io/prune: disabled` annotation and
> the `giantswarm.io/prevent-deletion` label. To delete the cluster, remove the
> labels and delete its `HelmRelease` by hand, see
> [Delete the cluster](../getting-started.md#6-delete-the-cluster-optional).

In our example we create one instance from each cluster environment base:

- for the dev environment we create [HELLO_APP_DEV_CLUSTER_1](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_DEV_CLUSTER_1/cluster/kustomization.yaml)
- for the staging environment we create [HELLO_APP_STAGING_CLUSTER_1](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_STAGING_CLUSTER_1/cluster/kustomization.yaml)

The dev and staging clusters run in `eu-central`. Production runs in two regions, and its clusters add their region's
extra node pool:

- for the production environment we create [HELLO_APP_PROD_CLUSTER_EU_CENTRAL](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster/kustomization.yaml)
- and another one in a different region with some different values for the cluster [HELLO_APP_PROD_CLUSTER_US_WEST](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_US_WEST/cluster/kustomization.yaml)

Every cluster lists the components that append to its `HelmRelease` `valuesFrom`: its region, optionally the region's
extra node pool, and last the cluster template's [userconfig](/bases/cluster_templates/hello_app_cluster/userconfig)
component, which appends the cluster's own `${cluster_name}-cluster-userconfig`. kustomize applies the components in
the order they are listed, so Flux merges the entries in this order:

1. `cluster-app-installation-values`, the management cluster's values (see the [cluster base](
   /bases/clusters/capa/template/readme.md#values-from-the-management-cluster))
1. `${cluster_name}-config`, the base values
1. `${cluster_name}-region-config`, the region
1. `${cluster_name}-region-node-pool-config`, the region's extra node pool, for the clusters that add it
1. `${cluster_name}-cluster-userconfig`, the cluster's own values

The cluster template doesn't append the cluster's own values itself. It is a resource of the cluster's kustomization,
and kustomize applies the patches of a resource before the components of the kustomization that uses it. A region
component would then land after the cluster's own values and override them.

> **Note**
>
> Always list the `userconfig` component. Without it, the `${cluster_name}-cluster-userconfig` ConfigMap is still
> created, but nothing reads it: the cluster silently loses its own values and those of its stage. CI doesn't catch
> this.

Let's take a look at the development environment instance. It runs in `eu-central`. The cluster's directory lists
`cluster/` in its own `kustomization.yaml`, so the cluster's `Kustomization` never applies an `out-of-band` directory
next to it to the management cluster.

```sh
mkdir -p HELLO_APP_DEV_CLUSTER_1/cluster

cat <<EOF > HELLO_APP_DEV_CLUSTER_1/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
components:
  - ../../../../../../../bases/environments/regions/eu_central
  - ../../../../../../../bases/cluster_templates/hello_app_cluster/userconfig
resources:
  - ../../../../../../../bases/environments/stages/dev/hello_app_cluster
EOF

cat <<EOF > HELLO_APP_DEV_CLUSTER_1/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - cluster/
EOF
```

The staging cluster looks the same with the staging stage.

The production clusters also add their region's extra node pool, between the region and the cluster's own values.

```bash
mkdir -p HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster
cat <<EOF > HELLO_APP_PROD_CLUSTER_EU_CENTRAL/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
components:
  - ../../../../../../../bases/environments/regions/eu_central
  - ../../../../../../../bases/environments/regions/eu_central/node_pool
  - ../../../../../../../bases/cluster_templates/hello_app_cluster/userconfig
resources:
  - ../../../../../../../bases/environments/stages/prod/hello_app_cluster
EOF

cat <<EOF > HELLO_APP_PROD_CLUSTER_EU_CENTRAL/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - cluster/
EOF
```

The `us-west` version of the production cluster uses the other region.

```bash
mkdir -p HELLO_APP_PROD_CLUSTER_US_WEST/cluster
cat <<EOF > HELLO_APP_PROD_CLUSTER_US_WEST/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
components:
  - ../../../../../../../bases/environments/regions/us_west
  - ../../../../../../../bases/environments/regions/us_west/node_pool
  - ../../../../../../../bases/cluster_templates/hello_app_cluster/userconfig
resources:
  - ../../../../../../../bases/environments/stages/prod/hello_app_cluster
EOF

cat <<EOF > HELLO_APP_PROD_CLUSTER_US_WEST/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - cluster/
EOF
```

> **Note**
>
> Don't insert the region's ConfigMap with a JSON patch at a fixed position, such as `/spec/valuesFrom/1`. The position
> is only right as long as the base has a given number of entries before it. When the base gains an entry, the region's
> values silently move before or after the wrong layer. The components append with `/spec/valuesFrom/-` and get their
> order from the `components:` list.

## Tips for developing environments

For complex clusters, you can end up merging a lot of layers of templates and configurations.
Under `tools` folder in this repository you can find the `fake-flux` script that helps
you render and inspect the final result. For more information check [tools/README.md](/tools/README.md).
