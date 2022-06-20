# Add Workload Cluster environments

You might want to set up multiple, similar Workload Clusters that serve as for example development,
staging and production environments. You can utilize [bases](/bases) to achieve that. Let's take a look at the
[/bases/environments](/bases/environments) folder structure.

## Environments

The `deployments` folder is a convenient wrapper to group our environment specifications.
There is a good reason for this additional layer of grouping. Think of the use case of having multiple
different clusters - like the dev, staging, production example - but also having multiple different
regions or data centers where you want to spin these clusters up.

Think that these cluster should in many regards look the same wherever they are. But also whatever cluster
is hosted in a given region or data center should use a specific IP range, certificates or ingresses.

In that cases we recommend putting region or data center specific configurations into for example
`/bases/environments/regions` folder and under there create a let's say `ap-east-1`, `eu-central-1`,
`us-west-2` folders.

Later you will reference all these layers in [/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters](
/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters)

### Deployments

We have 3 example clusters under [/bases/environments/deployments](/bases/environments/deployments):

- [dev](/bases/environments/deployments/dev)
- [staging](/bases/environments/deployments/staging)
- [prod](/bases/environments/deployments/prod)

Each of these contain a `hello_app_cluster` example.
This name might already be familiar to you from [Preparing a cluster definition template](./add_wc_template.md) section.

By checking each `kustomization.yaml` files - the [dev](
/bases/environments/deployments/dev/hello_app_cluster/kustomization.yaml) one for example - you will notice that they
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

#### The dev cluster

In [hello_app_cluster](/bases/cluster_templates/hello_app_cluster) base cluster template defines that the
[hello-web-app app set](/bases/app_sets/hello-web-app) should be installed in all of these clusters.
We can  provide overrides to the settings via the [hello_world_app_user_config.yaml](
/bases/environments/deployments/dev/hello_app_cluster/hello_world_app_user_config.yaml) file, for example
setting a lower thread pool size.

```yaml
thread_pool_size: 16
```

It also makes sense to configure `Automatic Updates` for our development cluster. We store these configurations under
the [/bases/environments/deployments/dev/hello_app_cluster/automatic_updates](
/bases/environments/deployments/dev/hello_app_cluster/automatic_updates) folder. You can read more about how
`Automatic Updates` work [here](/docs/apps/automatic_updates_appcr.md)

Now that we have automation set up around `Automatic Updates` we can set up our rules for the development cluster
on how it should update `Apps`. We need 2 things to achieve that, and we recommend setting up one multi-document YAML
files to store all these in a single place.

The [ImageRepository](https://fluxcd.io/docs/components/image/imagerepositories/) definitions to tell Flux
where to look for updates stored in: [imagerepositories.yaml](
/bases/environments/deployments/dev/hello_app_cluster/imagerepositories.yaml).

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
/bases/environments/deployments/dev/hello_app_cluster/imagepolicies.yaml).

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
- it has automatic updated set up

It also provides overrides to the [hello-web-app app set](/bases/app_sets/hello-web-app) via
[hello_world_app_user_config.yaml](
/bases/environments/deployments/staging/hello_app_cluster/hello_world_app_user_config.yaml).
We want this environment to be more close to production so let's say we set a larger thread pool size.

```yaml
thread_pool_size: 64
```

We also want the images automatically rolled out here to be more stable, so we have a slightly different
[imagepolicies.yaml](/bases/environments/deployments/staging/hello_app_cluster/imagepolicies.yaml) here where
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
/bases/environments/deployments/prod/hello_app_cluster/hello_world_app_user_config.yaml).

```yaml
thread_pool_size: 256
```

Notice however that we decided not to set up `Automatic Updates` for this cluster.

Instead, we use the `Kustomization` in the cluster's [kustomization.yaml](
/bases/environments/deployments/prod/hello_app_cluster/kustomization.yaml) to patch the exact versions to use
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
