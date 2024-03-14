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

Let's create the `kustomization.yaml` file for the development cluster.

```sh
cat <<EOF > kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
configMapGenerator:
  - behavior: create
    files:
      - values=hello_world_app_user_config.yaml
    name: \${cluster_name}-hello-world-user-config
generatorOptions:
  disableNameSuffixHash: true
kind: Kustomization
resources:
  - automatic_updates/
  - imagepolicies.yaml
  - imagerepositories.yaml
  - ../../../../cluster_templates/hello_app_cluster
EOF
```

In [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) base cluster template defines that the
[hello-web-app app set](/bases/app_sets/hello-web-app) should be installed in all of these clusters.
We can  provide overrides to the settings via the [hello_world_app_user_config.yaml](
/bases/environments/stages/dev/hello_app_cluster/hello_world_app_user_config.yaml) file, for example
setting a lower thread pool size.

```sh
cat <<EOF > hello_world_app_user_config.yaml
thread_pool_size: 16
EOF
```

It also makes sense to configure `Automatic Updates` for our development cluster. We store these configurations under
the [/bases/environments/stages/dev/hello_app_cluster/automatic_updates](
/bases/environments/stages/dev/hello_app_cluster/automatic_updates) folder. You can read more about how
`Automatic Updates` work [here](/docs/apps/automatic_updates_appcr.md)

```sh
mkdir automatic_updates

# Let's create the Kustomization for automatic updates
cat <<EOF > automatic_updates/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
commonLabels:
  giantswarm.io/managed-by: flux
kind: Kustomization
resources:
- catalog.yaml
- imageupdate.yaml
EOF

# Let's create the catalog
cat <<EOF > automatic_updates/catalog.yaml
apiVersion: application.giantswarm.io/v1alpha1
kind: Catalog
metadata:
  labels:
    application.giantswarm.io/catalog-visibility: internal
  name: giantswarm-catalog-oci
  namespace: org-${ORG_NAME}
spec:
  description: giantswarm-catalog-oci
  logoURL: "https://avatars.githubusercontent.com/u/7556340?s=60&v=4"
  storage:
    URL: oci://giantswarmpublic.azurecr.io/giantswarm-catalog/
    type: helm
  title: giantswarm-catalog-oci
EOF

# Let' create the image update automation for Flux
cat <<EOF > automatic_updates/imageupdate.yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageUpdateAutomation
metadata:
  name: \${cluster_name}-image-updates
  namespace: org-\${organization}
spec:
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: fluxcdbot@users.noreply.github.com
        name: fluxcdbot
      messageTemplate: |
        automated app upgrades:
        {{ range $image, $_ := .Updated.Images -}}
        - {{ $image.Repository }} to {{ $image.Identifier }}
        {{ end -}}
    push:
      branch: main
  interval: 1m0s
  sourceRef:
    kind: GitRepository
    name: ${GIT_REPOSITORY_NAME}
  update:
    path: ./management-clusters/MC_NAME
    strategy: Setters
EOF
```

Now that we have automation set up around `Automatic Updates` we can set up our rules for the development cluster
on how it should update `Apps`. We need 2 things to achieve that, and we recommend setting up one multi-document YAML
files to store all these in a single place.

The [ImageRepository](https://fluxcd.io/docs/components/image/imagerepositories/) definitions to tell Flux
where to look for updates stored in: [imagerepositories.yaml](
/bases/environments/stages/dev/hello_app_cluster/imagerepositories.yaml).

Let's tell Flux to look for available images for the `hello-world-app`
in the `giantswarmpublic.azurecr.io/giantswarm-catalog` registry every 10 minutes.

```sh
cat <<EOF > imagerepositories.yaml
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: \${cluster_name}-hello-app
  namespace: org-\${organization}
spec:
  image: giantswarmpublic.azurecr.io/giantswarm-catalog/hello-world-app
  interval: 10m0s
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: \${cluster_name}-simple-db-app
  namespace: org-\${organization}
spec:
  image: giantswarmpublic.azurecr.io/giantswarm-catalog/simple-db-app
  interval: 10m0s
EOF
```

The second half are the [ImagePolicy](https://fluxcd.io/docs/components/image/imagepolicies/) definitions to tell Flux
which versions it should automatically apply stored in: [imagepolicies.yaml](
/bases/environments/stages/dev/hello_app_cluster/imagepolicies.yaml).

Let's have Flux automatically roll out all `-dev` releases that are of at least version `0.1.0` or above.

```sh
cat <<EOF > imagepolicies.yaml
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: \${cluster_name}-hello-app
  namespace: org-\${organization}
spec:
  filterTags:
    pattern: '.*-dev.*'
  imageRepositoryRef:
    name: \${cluster_name}-hello-app
  policy:
    semver:
      range: '>=0.1.0'
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: \${cluster_name}-simple-db-app
  namespace: org-\${organization}
spec:
  imageRepositoryRef:
    name: \${cluster_name}-simple-db
  policy:
    semver:
      range: '>=0.1.0 <0.2.0'
EOF
```

We can also use `Kustomization` patches to set exact versions to use in the cluster's `kustomization.yaml` file.

```sh
cat <<EOF >> kustomization.yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/version
        value: '0.1.8
    target:
      kind: App
      name: \\\${cluster_name}-hello-world
  - patch: |-
      - op: replace
        path: /spec/version
        value: '0.1.0'
    target:
      kind: App
      name: \\\${cluster_name}-simple-db
EOF
```

And pretty much that is it for the development cluster. Let's look at the staging cluster next to the minor differences.

#### The staging cluster

Let's change our working directory to the staging cluster.

```sh
cd ../../staging/hello_app_cluster
```

We will use the same environment variables and `kustomization.yaml` for this cluster template as we did for the
development cluster.

It is similar to the development cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base
- it has automatic updates set up

It also provides overrides to the [hello-web-app app set](/bases/app_sets/hello-web-app) via
[hello_world_app_user_config.yaml](
/bases/environments/stages/staging/hello_app_cluster/hello_world_app_user_config.yaml).
We want this environment to be closer to production so let's say we set a larger thread pool size.

```sh
cat <<EOF > hello_world_app_user_config.yaml
thread_pool_size: 64
EOF
```

Setting up the `automatic_updates` folder and the `imagerepositories.yaml` files requires exactly the same steps
as we did above for the development cluster.

We also want the images automatically rolled out here to be more stable, so we have a slightly different
[imagepolicies.yaml](/bases/environments/stages/staging/hello_app_cluster/imagepolicies.yaml) here where
we tell Flux to automatically install all stable versions that are at least version `0.1.0` but we do not want
to automatically introduce possibly breaking changes in major version bump, so let's stay below `1.0.0`.

```sh
cat <<EOF > imagepolicies.yaml
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: \${cluster_name}-hello-app
  namespace: org-\${organization}
spec:
  imageRepositoryRef:
    name: \${cluster_name}-hello-app
  policy:
    semver:
      range: '>=0.1.0 <1.0.0'
---
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: \${cluster_name}-simple-db-app
  namespace: org-\${organization}
spec:
  imageRepositoryRef:
    name: \${cluster_name}-simple-db
  policy:
    semver:
      range: '>=0.1.0 <0.2.0'
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
  - behavior: create
    files:
      - values=hello_world_app_user_config.yaml
    name: \${cluster_name}-hello-world-user-config
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
  cloudConfig: cloud-config-giantswarm-2
  cloudName: openstack
  externalNetworkID: prod-bbbb-cccc-dddd-eeeeeeeeeeee
  nodeClasses:
    - bootFromVolume: true
      diskSize: 150
      flavor: n1.large
      image: dddddddd-dddd-dddd-dddd-dddddddddddd
      name: default
EOF
```

Then we provide some overrides to the [hello-web-app app set](/bases/app_sets/hello-web-app) via
[hello_world_app_user_config.yaml](
/bases/environments/stages/prod/hello_app_cluster/hello_world_app_user_config.yaml).

```yaml
cat <<EOF > hello_world_app_user_config.yaml
thread_pool_size: 256
EOF
```

Notice however that we decided not to set up `Automatic Updates` for this cluster.

Instead, we use the `Kustomization` in the cluster's [kustomization.yaml](
/bases/environments/stages/prod/hello_app_cluster/kustomization.yaml) to patch the exact versions to use
in out App CRs.

```sh
cat <<EOF >> kustomization.yaml
patches:
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.8
    target:
      kind: App
      name: \\\${cluster_name}-hello-world
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.0
    target:
      kind: App
      name: \\\${cluster_name}-simple-db
EOF
```

We tell Flux to use version `0.1.8` of `hello-world-app` and version `0.1.0` of `simple-db-app`.

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
