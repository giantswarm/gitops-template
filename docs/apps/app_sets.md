# Creating and using App Sets

- [Creating and using App Sets](#creating-and-using-app-sets)
  - [Limitations](#limitations)
  - [Example](#example)
    - [App Set Template](#app-set-template)
    - [Using App Set](#using-app-set)
  - [Creating an App Set Template](#creating-an-app-set-template)
  - [Using an App Set](#using-an-app-set)

It is often desireable to deploy a group of apps together, as a single deployment step. We call such groups "App Sets".
There's nothing special about App Sets: they are not a separate API entity, rather just a configuration pattern
enabled by `kustomize` and `flux`. The purpose of such approach can vary, but it's usually to meet the following benefits:

- Apps within the set have strong relationship and dependency on versions and you want to be sure that the correct
  versions are used and deployed together.
- Configuration of one app in a set depends on configuration of another app in the same set. By placing them together it
  is possible to simplify configuration of one app by providing values known to depend on another. As a result, it is
  easier to deploy an App Set than each of the apps individually. That way a specialized team might deliver a
  pre-configured App Set so that it is easy and understandable to deploy be a less proficient end user.

## Limitations

Even though App Sets have a lot of benefits, their implementation with `kustomize` and `flux` is pretty limited.
Please make sure that you read this section before deciding to implement App Sets the way they are described here.

In general, the whole problem can be summarized as "`kustomize` is not a templating engine". It can override some values,
even in bulks, but in can't put the same value in any arbitrary place.

In general case, it is impossible to configure a variable once and use it with multiple apps. There are only 2 choices
here: either each pair of apps shares exactly the same ConfigMap/Secret as a `config:` attribute of an App CR or they
use two separate ConfigMaps. In the latter case, it is your responsibility to provide exactly the same value in both
ConfigMaps/Secrets. In the former, it means that your apps share the same configuration input and must be able to
handle this situation correctly: there can be no conflicting options and each shared option must be understood exactly
the same by each app. In practice, it means that the apps must be prepared on Helm chart layer to work together.
If none of these two solutions is applicable, you might want to solve the problem of bundling the apps together
elsewhere. One of possible routes is to create a new umbrella Helm Chart that includes all the necessary apps
as [sub-charts](https://helm.sh/docs/chart_template_guide/subcharts_and_globals/).

## Example

### App Set Template

An example of an App Set Template is available in [bases/app_sets/hello-web-app](../../bases/app_sets/hello-web-app/).
This App Set assumes, that it's impossible to build a shared ConfigMap for both Apps and as such does full config
override on App Set template level and override using `userConfig:` field in App Set instance.

### Using App Set

An example showing how to use an App Set is available in
[aWC_NAME/app_sets/hello-web-app-1](../../management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/app_sets/hello-web-app-1).

## Creating an App Set Template

Creating an App Set Template is not much different than [creating an App Template](add_app_template.md). Please check the
docs there first, if yoo haven't already.

To get started, go to the `bases` directory and create a subdirectory for your App Set Template. In this directory,
create a `kustomization.yaml` similar to the one below:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
commonLabels:
  gitops.giantswarm.io/appSet: hello-web-app # this label will be applied to all resources included in the App Set
# (optional) replace default config of apps included in the set
configMapGenerator:
  - behavior: replace
    files:
    - values=default_config_simple_db.yaml
    name: ${cluster_id}-simple-db-values # has to be in sync with the name used by included app
  - behavior: replace
    files:
    - values=default_config_hello_world.yaml
    name: ${cluster_id}-hello-world-values # has to be in sync with the name used by included app
# block end
kind: Kustomization
namespace: hello-web # (optional) enforce the same namespace for all the apps in the set
# (optional) here we can enforce versions for both apps that we know work well together
patches:
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.9
    target:
      kind: App
      name: hello-world
  - patch: |-
      - op: replace
        path: /spec/version
        value: 0.1.1
    target:
      kind: App
      name: simple-db
# block end
resources:
  - ../../apps/hello-world
  - ../../apps/simple-db
```

Please note the following in the example above:

- We use the `gitops.giantswarm.io/appSet: YOUR_NAME` that will identify all the components included in the App Set.
  This makes debugging easier later, as you can easily find what belongs to the Set after it is deployed.
- One of the key benefits of App Sets is to be able to provide a specific set of app versions, that is known to make
  the apps work well together. Over here, we do that as a set of in-line patches, so it is immediately visible
  in the `kustomization.yaml` file which versions are used.
- When using `App` CRs, we have two configuration slots available: `config` and `userConfig`. Since we always want
  to leave `userConfig` at the end users disposal, we're left with overriding the whole ConfigMap coming from the
  base application as the only option.
- It is recommended to re-use App Templates to create App Set Templates. That's exactly what we do here: apps defined
  in the `resources:` block are App Templates, that, if needed, can be also used standalone.
- The example above doesn't cover handling Secrets - we do that for brevity. Secrets can be created the same way as in
  normal [App Templates](./add_app_template.md) and overrode the same as ConfigMaps or Secrets when creating
  [App from a Template](./add_appcr.md#adding-app-using-app-template).

## Using an App Set

Using an App Set Template is once again very similar to using a single
[App Set](./add_appcr.md#adding-app-using-app-template). To create one, save a path that contains your desired
App Set Template in the [bases/app_sets](../../bases/app_sets/) directory. Then, create a new directory in the
`app_sets` directory of your Working Cluster. In that directory, create a `kustomization.yaml` file based on the
following pattern:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
buildMetadata: [originAnnotations]
configMapGenerator:
  - files:
      - values=override_config_hello_world.yaml
    name: ${cluster_id}-hello-world-user-values
generatorOptions:
  disableNameSuffixHash: true
kind: Kustomization
namespace: hello-web-team1
patchesStrategicMerge:
  - config_patch.yaml
resources:
  - ../../../../../../../../bases/app_sets/hello-web-app
```

Over here, we are overriding the configuration of the `hello-world` app, which was already defined in the App Set
Template. Since here we're using the `userConfig` property, we don't have to override the whole config, but only YAML
keys we need to change. One more important fact is that we're setting a custom Namespace for the whole deployment of an
app. If you want to learn more about how config overrides work, please consult our
[docs about creating apps](add_appcr.md), as in general App Set is just a bundle of them.
