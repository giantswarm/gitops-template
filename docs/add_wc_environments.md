# Add Workload Cluster environments

- [General note](#general-note)
- [Environments](#environments)
  - [Stages](#stages)
    - [The development cluster](#the-development-cluster)
    - [The staging cluster](#the-staging-cluster)
    - [The production cluster](#the-production-cluster)
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

Each of these contain a `hello_app_cluster` example.
This name might already be familiar to you from [Preparing a cluster definition template](./add_wc_template.md) section.

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

Let's create the `kustomization.yaml` file for the development cluster.

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
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

And pretty much that is it for the development cluster. Let's look at the staging cluster next to the minor differences.

#### The staging cluster

Let's change our working directory to the staging cluster.

```sh
cd ../../staging/hello_app_cluster
```

We will use the same environment variables for this cluster template as we did for the development cluster.

It is similar to the development cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base
- it has automatic updates set up

We want the versions automatically rolled out here to be more stable, so we tell Flux to automatically install all
stable versions that are at least version `3.0.0`, but we do not want to automatically introduce possibly breaking
changes in a major version bump, so let's stay below `4.0.0`. A range without a pre-release comparator never matches a
pre-release tag, so no filter is needed.

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
          semver: '>=3.0.0 <4.0.0'
    target:
      kind: OCIRepository
      name: \\\${cluster_name}-hello-world
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

So basically our staging cluster in our example is a smaller scale cluster carrying stable versions of our applications.

Now, let's take a look at the production cluster example.

#### The production cluster

Let's change our working directory to the staging cluster.

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
      - values=cluster_user_config.yaml
    name: \${cluster_name}-user-config
    namespace: org-\${organization}
generatorOptions:
  disableNameSuffixHash: true
kind: Kustomization
resources:
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

It is similar to the staging cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base

Note in the `kustomization.yaml` above that we create another `ConfigMap` for the production cluster
that contains some extra settings for our cluster.

```sh
cat <<EOF > cluster_user_config.yaml
values: |
  global:
    nodePools:
      xxxxx:
        instanceType: m6i.4xlarge
EOF
```

Notice however that we decided not to set up `Automatic Updates` for this cluster.

Instead, we use the `Kustomization` in the cluster's [kustomization.yaml](
/bases/environments/stages/prod/hello_app_cluster/kustomization.yaml) to patch the exact versions to use
in our `OCIRepository` resources.

```sh
cat <<EOF >> kustomization.yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/ref/tag
        value: "3.2.2"
    target:
      kind: OCIRepository
      name: \\\${cluster_name}-hello-world
EOF
```

We tell Flux to use version `3.2.2` of the `hello-world` app.

In this example when we sufficiently validated our released changes in the staging environment we update the versions
in the `Kustomization`, merge the change and let Flux do the work.

#### Region specific settings for the production cluster

Let's create some bases for our region setup. Relative to root of the repository let's execute the following commands.

```bash
mkdir -p bases/environments/regions/eu_central
mkdir -p bases/environments/regions/us_west

cd bases/environments/regions
```

For the `eu-central` region.

```bash
cat <<EOF >> eu_central/cluster_config.yaml
controlPlane:
  availabilityZones:
    - eu-central-1
    - eu-central-2
    - eu-central-3
nodeCIDR: "10.32.0.0/24"
EOF

cat <<EOF >> eu_central/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
configMapGenerator:
  - files:
    - values=cluster_config.yaml
    name: ${cluster_name}-region-config
    namespace: org-${organization}
generatorOptions:
  disableNameSuffixHash: true
kind: Kustomization
EOF
```

And for the `us-west` region.

```bash
cat <<EOF >> us_west/cluster_config.yaml
controlPlane:
  availabilityZones:
    - us-west-1
    - us-west-2
nodeCIDR: "10.64.0.0/24"
EOF

cat <<EOF >> us_west/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
configMapGenerator:
  - files:
    - values=cluster_config.yaml
    name: ${cluster_name}-region-config
    namespace: org-${organization}
generatorOptions:
  disableNameSuffixHash: true
kind: Kustomization
EOF
```

We will use these as a second base for our production clusters.

## Add Workload Clusters based on the environment cluster templates

Just as any other Workload Clusters we define them in
[/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters).

Relative to the root of the repository, let's change our working directory to our `workload-clusters` folder.

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters
```

Then let's tell Flux to manage our cluster instance.

```sh
cat <<EOF > HELLO_APP_DEV_CLUSTER_1.yaml
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: clusters-\${cluster_name}
  namespace: default
spec:
  interval: 1m
  path: "./management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/HELLO_APP_DEV_CLUSTER_1/mapi"
  postBuild:
    substitute:
      cluster_domain: "MY_DOMAIN"
      cluster_name: "HELLO_APP_DEV_1"
      cluster_release: "0.8.1"
      default_apps_release: "0.2.0"
      organization: "${ORG_NAME}"
  prune: false
  serviceAccountName: automation
  sourceRef:
    kind: GitRepository
    name: ${GIT_REPOSITORY_NAME}
  timeout: 2m

EOF
```

> **Note**
>
> In this example, we specifically set the `prune` value to `false`.
>
> This is to ensure that in the event of accidental deletion or modification of
> the Kustomiation resource, clusters are not automatically deleted as part of
> the cleanup action carried out by Flux.
>
> It is recommended, and considered good practice that this remains `false`
> until such time that a cluster is specifically being deleted.
>
> In this instance, two commits should be made.
>
> 1. To explicitly set `prune: true` along with a commit message detailing why.
> 1. To delete the Kustomization controlling this cluster.

In our example we create one instance from each cluster environment base:

- for the dev environment we create [HELLO_APP_DEV_CLUSTER_1](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_DEV_CLUSTER_1/mapi/cluster/kustomization.yaml)
- for the staging environment we create [HELLO_APP_STAGING_CLUSTER_1](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_STAGING_CLUSTER_1/mapi/cluster/kustomization.yaml)

And for production we will take it one step further by splitting it into multiple data regions using multiple bases.

- for the production environment we create [HELLO_APP_PROD_CLUSTER_EU_CENTRAL](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_EU_CENTRAL/mapi/cluster/kustomization.yaml)
- and another one in a different region with some different configuration for the cluster App CR [HELLO_APP_PROD_CLUSTER_US_WEST](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_US_WEST/mapi/cluster/kustomization.yaml)

All of their `kustomization.yaml` look very similar. Let's take a look at the development environment instance.

```sh
mkdir HELLO_APP_DEV_CLUSTER_1

cat <<EOF > HELLO_APP_DEV_CLUSTER_1/mapi/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
resources:
  - ../../../../../../../../bases/environments/stages/dev/hello_app_cluster
EOF
```

It basically just references our environment base. But in more complex examples it could do more.

Think back on the example of having multiple regions where you need to set specific configurations.
In such a case you would end up with the below setup.

Let's set up a workload cluster both `eu-central` and `us-west` regions that we created some environment bases for.

Note that we use the extra configs feature of App CR to patch in additional layers of configurations for out Application.
You can read more about this feature [here](https://docs.giantswarm.io/app-platform/app-configuration/#extra-configs).

And the kustomization for this cluster looks like.

```bash
cat <<EOF >> HELLO_APP_PROD_CLUSTER_EU_CENTRAL/mapi/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
patches:
  - patch: |
      - op: add
        path: /spec/extraConfigs/-
        value:
          # See: https://docs.giantswarm.io/app-platform/app-configuration/#extra-configs
            name: "${cluster_name}-region-config"
            namespace: org-${organization}
    target:
      group: application.giantswarm.io
      kind: App
      name: \${cluster_name}
      namespace: org-\${organization}
      version: v1alpha1
resources:
  - ../../../../../../../../bases/environments/stages/prod/hello_app_cluster
  - ../../../../../../../../bases/environments/regions/eu_central
```

For the `us-west` region version of the production cluster we need to create the same patch for the cluster App CR.
The resultant `kustomization.yaml` looks like the one below.

```bash
cat <<EOF >> HELLO_APP_PROD_CLUSTER_US_WEST/mapi/cluster/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
patches:
  - patch: |
      - op: add
        path: /spec/extraConfigs/-
        value:
          # See: https://docs.giantswarm.io/app-platform/app-configuration/#extra-configs
            name: "${cluster_name}-region-config"
            namespace: org-${organization}
    target:
      group: application.giantswarm.io
      kind: App
      name: \${cluster_name}
      namespace: org-\${organization}
      version: v1alpha1
resources:
  - ../../../../../../../../bases/environments/stages/prod/hello_app_cluster
  - ../../../../../../../../bases/environments/regions/us_west
```

## Tips for developing environments

For complex clusters, you can end up merging a lot of layers of templates and configurations.
Under `tools` folder in this repository you can find the `fake-flux-build` script that helps
you render and inspect the final result. For more information check [tools/README.md](/tools/README.md).
