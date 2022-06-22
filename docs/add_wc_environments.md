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

Each of these approaches has pros and cons. Over here, we're proposing the multi-directory approach. The pros of it are:
a single repo and branch serving as the source of truth for all the environments, very easy template sharing and
relatively easy way to compare and promote configuration across environments. On the other hand, it might not be the
best solution for access control, templates versioning and also easy comparing of environments.

## Environments

The `stages` folder is how we propose to group environment specifications.
There is a good reason for this additional layer of grouping. You can use this approach to have multiple
different clusters - like the dev, staging, production - but also to have multiple different
regions or data centers where you want to spin these clusters up.

We're assuming that all the clusters using this environments pattern should in many regards look the same
across all the environments. Still, each environment layer introduces some key differences, like app version being deployed
for `dev/staging/prod` environments or a specific IP range, certificate or ingresses config for data center related environments
like `us-east-1/us-west-2`.

To create an environment template, you need to make a  directory in `environments` that describes the best the
differentating factor for that kind of environment, then you should create subfolder there for different possible values.
For example, for multiple data centers, we recommend putting region specific configuration into
`/bases/environments/regions` folder and under there create `ap-east-1`, `eu-central-1` and `us-west-2` folders.

Once your environment templates are ready, you can use them to create new clusters by placing cluster definitions in
in [/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters)

> :construction: Please note that if you want to use multiple environment templates to create a single cluster
that uses `App CR`s for deployments, like you would like to use `dev` out of `staging` layout to set app configuration
and then use `east` from the `data-centers` to set the IP ranges, you will run into issues around merging
configurations, as currently one configuration source (ie. `ConfigMap` in `spec.config.configMap`) completely
overrides the whole value of the same attribute coming from the other base. We're working to remove this limitation.

### Stages

We have 3 example clusters under [/bases/environments/stages](/bases/environments/stages):

- [dev](/bases/environments/stages/dev)
- [staging](/bases/environments/stages/staging)
- [prod](/bases/environments/stages/prod)

Each of these contain a `hello_app_cluster` example.
This name might already be familiar to you from [Preparing a cluster definition template](./add_wc_template.md) section.

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

In [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) base cluster template defines that the
[hello-web-app app set](/bases/app_sets/hello-web-app) should be installed in all of these clusters.
We can  provide overrides to the settings via the [hello_world_app_user_config.yaml](
/bases/environments/stages/dev/hello_app_cluster/hello_world_app_user_config.yaml) file, for example
setting a lower thread pool size.

```yaml
thread_pool_size: 16
```

It also makes sense to configure `Automatic Updates` for our development cluster. We store these configurations under
the [/bases/environments/stages/dev/hello_app_cluster/automatic_updates](
/bases/environments/stages/dev/hello_app_cluster/automatic_updates) folder. You can read more about how
`Automatic Updates` work [here](/docs/apps/automatic_updates_appcr.md)

Now that we have automation set up around `Automatic Updates` we can set up our rules for the development cluster
on how it should update `Apps`. We need 2 things to achieve that, and we recommend setting up one multi-document YAML
files to store all these in a single place.

The [ImageRepository](https://fluxcd.io/docs/components/image/imagerepositories/) definitions to tell Flux
where to look for updates stored in: [imagerepositories.yaml](
/bases/environments/stages/dev/hello_app_cluster/imagerepositories.yaml).

Let's tell Flux to look for available images for the `hello-world-app`
in the `giantswarmpublic.azurecr.io/giantswarm-catalog` registry every 10 minutes.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: ${cluster_id}-hello-app
spec:
  image: giantswarmpublic.azurecr.io/giantswarm-catalog/hello-world-app
  interval: 10m0s
```

The second half are the [ImagePolicy](https://fluxcd.io/docs/components/image/imagepolicies/) definitions to tell Flux
which versions it should automatically apply stored in: [imagepolicies.yaml](
/bases/environments/stages/dev/hello_app_cluster/imagepolicies.yaml).

Let's have Flux automatically roll out all `-dev` releases that are of at least version `0.1.0` or above.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: ${cluster_id}-hello-app
spec:
  filterTags:
    pattern: '.*-dev.*'
  imageRepositoryRef:
    name: ${cluster_id}-hello-app
  policy:
    semver:
      range: '>=0.1.0'
```

And pretty much that is it for the development cluster. Let's look at the staging cluster next to the minor differences.

#### The staging cluster

It is similar to the development cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base
- it has automatic updates set up

It also provides overrides to the [hello-web-app app set](/bases/app_sets/hello-web-app) via
[hello_world_app_user_config.yaml](
/bases/environments/stages/staging/hello_app_cluster/hello_world_app_user_config.yaml).
We want this environment to be closer to production so let's say we set a larger thread pool size.

```yaml
thread_pool_size: 64
```

We also want the images automatically rolled out here to be more stable, so we have a slightly different
[imagepolicies.yaml](/bases/environments/stages/staging/hello_app_cluster/imagepolicies.yaml) here where
we tell Flux to automatically install all stable versions that are at least version `0.1.0` but we do not want
to automatically introduce possibly breaking changes in major version bump, so let's stay below `1.0.0`.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: ${cluster_id}-hello-app
spec:
  imageRepositoryRef:
    name: ${cluster_id}-hello-app
  policy:
    semver:
      range: '>=0.1.0 <1.0.0'
```

So basically our staging cluster in our example is a smaller scale cluster carrying stable versions of our applications.

Now, let's take a look at the production cluster example.

#### The production cluster

It is similar to the staging cluster in the following manners:

- it is based on the [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) template base

Then it provides some overrides to the [hello-web-app app set](/bases/app_sets/hello-web-app) via
[hello_world_app_user_config.yaml](
/bases/environments/stages/prod/hello_app_cluster/hello_world_app_user_config.yaml).

```yaml
thread_pool_size: 256
```

Notice however that we decided not to set up `Automatic Updates` for this cluster.

Instead, we use the `Kustomization` in the cluster's [kustomization.yaml](
/bases/environments/stages/prod/hello_app_cluster/kustomization.yaml) to patch the exact versions to use
in out App CRs.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
# ...
patches:
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.8
    target:
      kind: App
      name: \${cluster_id}-hello-world
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.0
    target:
      kind: App
      name: \${cluster_id}-simple-db
```

We tell Flux to use version `0.1.8` of `hello-world-app` and version `0.1.0` of `simple-db-app`.

In this example when we sufficiently validated our released changes in the staging environment we update the versions
in the `Kustomization`, merge the change and let Flux do the work.

## Add Workload Clusters based on the environment cluster templates

Just as any other Workload Clusters we define them in
[/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters).

In our example we create one instance from each cluster environment base:

- from the dev environment we create [HELLO_APP_DEV_CLUSTER_1](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_DEV_CLUSTER_1/kustomization.yaml)
- from the staging environment we create [HELLO_APP_STAGING_CLUSTER_1](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_STAGING_CLUSTER_1/kustomization.yaml)
- from the dev environment we create [HELLO_APP_PROD_CLUSTER_1](
  /management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/HELLO_APP_PROD_CLUSTER_1/kustomization.yaml)

All of their `kustomization.yaml` look very similar. Let's take a look at the development environment instance.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
resources:
  - ../../../../../../bases/environments/stages/dev/hello_app_cluster
```

It basically just references our environment base. But in more complex examples it could do more.

Think back on the example of having multiple regions or data centers where you need to set specific
configurations. In such a case you would end upt with something like the below setup.

You have workload cluster for each of them as `HELLO_APP_DEV_CLUSTER_AP_EAST_1`, `HELLO_APP_DEV_CLUSTER_EU_CENTRAL_1`
and `HELLO_APP_DEV_CLUSTER_US_WEST_2`. Their `kustomization.yaml` would look something like this.

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
kind: Kustomization
resources:
  - ../../../../../../bases/environments/stages/dev/hello_app_cluster
  - ../../../../../../bases/environments/regions/[[ REGION_NAME ]]
```

## Tips for developing environments

For complex clusters, you can end up merging a lot of layers of templates and configurations.
Under `tools` folder in this repository you can find the `fake-flux-build` script that helps
you render and inspect the final result. For more information check [tools/README.md](/tools/README.md).