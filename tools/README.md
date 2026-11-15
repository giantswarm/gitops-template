# Tools

## Requirements

The tools provided here may require the following external tools

- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [yq](https://github.com/mikefarah/yq)
- [yamllint](https://github.com/adrienverge/yamllint)
- [kubeconform](https://github.com/yannh/kubeconform); CI uses 0.8.0
- `curl`, `sha256sum` and `tar`, to fetch the Flux CRD schemas
- [flux](https://fluxcd.io/flux/installation/#install-the-flux-cli)
- [kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/binaries/)
- [helm](https://helm.sh/docs/intro/install/), for `validate-helm-values`

## Provides

This directory provides the following tools

- [test-all-ff](https://github.com/giantswarm/gitops-template/blob/main/tools/test-all-ff)
- [fake-flux](https://github.com/giantswarm/gitops-template/blob/main/tools/fake-flux)
- [validate-helm-values](https://github.com/giantswarm/gitops-template/blob/main/tools/validate-helm-values)

## `test-all-ff`

You can use this bash tool under a repository based on this template to verify the syntax of your manifests.

This tool will run through `yamllint`, `kubeconform` and `validate-helm-values` to verify your manifests pass all
checks and is likely to succeed in the cluster.

It runs `fake-flux` under the hood for each kustomization it finds

`kubeconform` runs with `-strict`, so unknown fields fail, and without `-ignore-missing-schemas`, so an object whose
kind has no schema fails instead of being skipped. The script looks up schemas in this order:

1. Kubernetes `v1.36.5`, the version of the Giant Swarm management clusters, from
   [yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) at a pinned commit.
2. Flux `v2.7.5`, the Flux that `flux-app` 1.12.2 runs on the management clusters, from the `crd-schemas.tar.gz` that Flux
   publishes with each release. The script downloads it once, checks its SHA-256 and keeps it under
   `${TMPDIR:-/tmp}/gitops-template-schemas`.
3. Giant Swarm CRDs such as `Organization`, from [giantswarm/json-schema](https://github.com/giantswarm/json-schema)
   at a pinned commit.

The versions are variables at the top of `test-all-ff`. If you add a resource whose kind is in none of these sources,
add a `-schema-location` for it to the script.

### test-all-ff usage

- `validate` Tests all found flux kustomizations with `yamllint`, `kubeconform` and `validate-helm-values`
- `template` Prints the entire repo manifest

## `validate-helm-values`

`validate-helm-values <manifest.yaml>` renders the chart of every Flux `HelmRelease` in a rendered manifest with
`helm template`, using the values the `HelmRelease` would get on the cluster. It fails when Helm rejects them, for
example because a key is misspelled and the chart's `values.schema.json` doesn't allow it. `test-all-ff validate`
runs it for every Flux `Kustomization`.

The values come from the `HelmRelease`'s `valuesFrom` entries, in order, followed by `spec.values`. Helm merges them
the same way Flux does: maps are merged, and lists and scalars are replaced. The chart comes from the `OCIRepository`
the `HelmRelease` references, or from a `HelmRepository`, and is cached under `${TMPDIR:-/tmp}/gitops-template-charts`.
A semver range is resolved to the newest matching version, as Flux would resolve it.

Some values don't exist until the cluster runs. They are replaced by stubs in [values-stubs](values-stubs/):

- `cluster-values.yaml` replaces the `<cluster>-cluster-values` ConfigMap, which cluster-apps-operator creates for
  each workload cluster.
- `cluster-app-installation-values.yaml` replaces the `cluster-app-installation-values` ConfigMap, which holds the
  management cluster's values, such as `global.managementCluster`. A Kyverno policy copies it into every `org-*`
  namespace of a Giant Swarm management cluster; see the [cluster base](/bases/clusters/capa/template/readme.md).
- `charts/<chart>.yaml` holds values a chart can't render without the management cluster, such as
  `release-aws`'s switch to render without looking up its Release resource. It is the first values file, so values
  from the repository override it. It doesn't set the region: a cluster that doesn't set its own must fail.

Two more checks fail, also for a `HelmRelease` listed in `validate-helm-values.ignore`, which only excuses Helm's
errors:

- A cluster without a region. A `HelmRelease` of a cluster chart fails when its merged values have no region. Without
  one, `release-aws` takes the region of the management cluster's nodes and `release-azure` its default location, so
  the cluster would be created somewhere nobody chose. The table `region_keys` in the script names the key per chart:
  `global.providerSpecific.region` for `release-aws` and `global.providerSpecific.location` for `release-azure`. A
  `release-*` chart that isn't in the table isn't checked, and the script prints a note. An AWS cluster sets its region
  with a component from `bases/environments/regions`, see [Regions](/docs/guides/environments.md#regions).
- A cluster that doesn't read its own values. A `<cluster>-cluster-userconfig` ConfigMap that no `HelmRelease` in the
  same build has in its `valuesFrom` fails, naming the cluster. That happens when a cluster made from a cluster
  template leaves out the template's userconfig component: the ConfigMap is still created, but the cluster loses its
  own values and those of its stage.

The check leaves out:

- SOPS-encrypted Secrets, because CI has no key to decrypt them.
- Optional `valuesFrom` entries that aren't in the repository.
- `valuesFrom` entries with a `targetPath`. The script prints a note when it skips one.

A `valuesFrom` entry that isn't optional and isn't in the repository fails the check.

[validate-helm-values.ignore](validate-helm-values.ignore) lists `HelmRelease`s whose errors are known. The script still
renders them and prints the errors, but they don't fail the check. An entry that renders without errors fails the check,
so the list can't go stale.

## `fake-flux`

Fake flux is a script that can emulate the behaviour of flux locally before committing your changes to your repository.

It's purpose is to support you in the detection of issues which may arise from syntax errors, failing patches or other
issues caused by incompatibilities with the flux ecosystem.

For a detailed description of what this tool can do, please see `fake-flux usage` which includes a comprehensive set of
examples.

### fake-flux usage

- `list` Lists all fluxcd kustomizations found in the current repository
- `build <kustomization> [path] [--use-kustomize] [yqflags] [query]` Build the given kustomization and optionally filter
   it for specific resources.

#### Arguments

> Argument order is important. The script will fail if the arguments are not given in the order specified.

- `<kustomization>` May be:
  - A number. The index provided for a kustomization when running `fake-flux list`
  - A name. Must be unique to the repository
  - `name:namespace` To target a specific kustomization in a given namespace. Use a single `:` to separate.

#### Optional Arguments

- `path` The path element is a subpath matching below the path defined in the kustomization you are parsing.
  For example, if the kustomization 'spec.path' is './management-clusters/example/organizations/dev/workload-clusters/dev/mapi'
  then 'path' must be a relative path below this, e.g. 'apps/athena'

- `--use-kustomize` Use kustomize to build the kustomization and not 'flux build'

- `yqflags` Optional flags to pass to 'yq'. Use -M to turn off output coloring. See `yq --help` for available flags.
  Does not work with multi-parameter arguments.

- `query` This must be a valid 'yq' query and can be used to filter for specific resources.
           output coloring can be turned off using -M before the query

- `<kustomization>` May be:
  - A number from the list given with `fake-flux list`
  - A name matching a unique kustomization in the set
  - `name:namespace` targetting a specific kustomization in a given namespace

### Examples

- Build all resources for kustomization by numeric index

  ```bash
  fake-flux build 1
  ```

- Build all resources for kustomization by kustomization name

  ```bash
  fake-flux build prod-cluster
  ```

- Build the kustomization "prod" in the "org-example" namespace

  ```bash
  fake-flux build prod:org-example
  ```

- Build all by index but target the apps/athena subpath

  ```bash
  fake-flux build 1 apps/athena
  ```

- Build all by name and select all apps with the name athena

  ```bash
  fake-flux build prod-cluster 'select(.kind == "App" and .metadata.name == "athena")'
  ```

- Build only the athena app and select the App CR

  ```bash
  fake-flux build 1 apps/athena 'select(.kind == "App")'
  ```

- Build only the athena app and select the App CR, turning off output coloring

  ```bash
  fake-flux build 1 apps/athena -M 'select(.kind == "App")'
  ```

- Build only the athena app and select the App CR, turning off output coloring. Use kustomize for rendering, not flux

  ```bash
  fake-flux build 1 apps/athena --use-kustomize -M 'select(.kind == "App")'
  ```

### Caveats

- This script cannot carry out replacements which may come from secrets or configmaps.
- When running in its default mode which uses `flux build kustomization`, secret data is replaced with the type of
  encryption used for that secret. To see the full encrypted secret, use the additional flag `--use-kustomize` which
  changes the build mechanism from `flux` to `kustomize`
- Secrets cannot be decrypted by this script or the underlying tools even if you have the keys locally. If you wish to
  see the output with the decrypted secrets, you must decrypt them first.

### Examples of the differences in behaviour between flux and kustomize for secrets

When running with `flux build` your secret output will look like this:

```yaml
apiVersion: v1
data:
  values: KipTT1BTKio=
kind: Secret
metadata:
  annotations:
    config.kubernetes.io/origin: |
      path: encrypted-secret.enc.yaml
  creationTimestamp: null
  labels:
    kustomize.toolkit.fluxcd.io/name: example
    kustomize.toolkit.fluxcd.io/namespace: default
  name: encrypted-secret-user-values
  namespace: example
```

Decoding the value will show:

```nohighlight
**SOPS**
```

When using `kustomize` as the build engine, the secret will be more verbose and contain encrypted values

```yaml
apiVersion: v1
data:
  values: ENC[AES256_GCM,data:<<<ENCRYPTED_MESSAGE>>>,tag:TAG_VALUE,type:str]
kind: Secret
metadata:
  annotations:
    config.kubernetes.io/origin: |
      path: encrytped-secret.enc.yaml
  creationTimestamp: null
  name: encrypted-secret-user-values
  namespace: example
sops:
  age: []
  azure_kv: []
  encrypted_regex: ^(data|stringData)$
  gcp_kms: []
  hc_vault: []
  kms: []
  lastmodified: "2023-01-26T12:50:50Z"
  mac: ENC[AES256_GCM,data:<<<ENCRYPTED_MAC>>>,tag:TAG_VALUE,type:str]
  pgp:
    - created_at: "2023-01-26T12:50:49Z"
      enc: |
        -----BEGIN PGP MESSAGE-----
        <<<PUBLIC KEY>>>
        -----END PGP MESSAGE-----
      fp: <<<FINGERPRINT>>>
  version: 3.7.3
```
