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
- [check-directory-readmes](https://github.com/giantswarm/gitops-template/blob/main/tools/check-directory-readmes)

## `test-all-ff`

You can use this bash tool under a repository based on this template to verify the syntax of your manifests.

This tool will run through `yamllint`, `kubeconform` and `validate-helm-values` to verify your manifests pass all
checks and is likely to succeed in the cluster.

It runs `fake-flux` under the hood for each kustomization it finds that applies this repository: one whose source is
the source of `MC_NAME.yaml`, the Kustomization that applies the directory its file is in, as in
`check-kustomization-paths`. It skips the others, such as an application team's, whose path is in the team's
repository, and says so. It fails if it finds none. `fake-flux` runs `flux build` with
`--strict-substitute`, so a variable that the manifests use but `spec.postBuild.substitute` doesn't set fails the build.

`kubeconform` runs with `-strict`, so unknown fields fail, and without `-ignore-missing-schemas`, so an object whose
kind has no schema fails instead of being skipped. It also checks the objects a Flux Operator `ResourceSet` renders,
which `validate-helm-values --expand` adds to the manifest: the `ResourceSet`'s own schema accepts any field in them.
`test-all-ff validate` checks that with
[testdata/resource-set-unknown-field.yaml](testdata/resource-set-unknown-field.yaml). The script looks up schemas in
this order:

1. Kubernetes `v1.36.5`, the version of the Giant Swarm management clusters, from
   [yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) at a pinned commit.
2. Flux `v2.7.5`, the Flux that `flux-app` 1.12.2 runs on the management clusters, from the `crd-schemas.tar.gz` that Flux
   publishes with each release. The script downloads it once, checks its SHA-256 and keeps it under
   `${TMPDIR:-/tmp}/gitops-template-schemas`.
3. Giant Swarm CRDs such as `Organization`, from [giantswarm/json-schema](https://github.com/giantswarm/json-schema)
   at a pinned commit.
4. Other CRDs, such as Kyverno's `ClusterPolicy` and External Secrets Operator's `ExternalSecret`, from
   [datreeio/CRDs-catalog](https://github.com/datreeio/CRDs-catalog) at a pinned commit.

The versions are variables at the top of `test-all-ff`. If you add a resource whose kind is in none of these sources,
add a `-schema-location` for it to the script.

### test-all-ff usage

- `validate` Tests all found flux kustomizations with `yamllint`, `kubeconform` and `validate-helm-values`
  - It also builds each base in `bases/secret_stores` with `kubectl kustomize` and checks it with `kubeconform`. They
    read cloud secret managers, so no cluster in the repository uses them and no Kustomization builds them.
- `template` Prints the entire repo manifest

## `check-directory-readmes`

Every directory a customer reads, copies or edits explains itself with a README. `check-directory-readmes` makes sure
of it: it walks `bases/` and `management-clusters/`, and fails for a directory without a `README.md` (or `readme.md`).
`tests/`, `tools/`, `.github/` and `docs/` are left out. pre-commit runs it, so CI does too, also on a pull request
that changes only Markdown.

Some leaves are copies of one shape, such as the stages, the regions or an example cluster's `cluster/` and `apps/`.
One README in the parent covers them, and the `COVERED` list at the top of the script names each one with its parent.
The check fails for an entry whose directory is gone, and for a parent README that doesn't name a leaf it covers, as
its path relative to the parent followed by a slash, such as `dev/`.

When you add a directory, give it a README. If it's another copy of a shape a parent README already describes, list it
in `COVERED` and name it in that README instead.

`test-all-ff validate` checks that the script fails in each of those cases.

### check-directory-readmes usage

Run it from the repository root, or pass the root as the only argument: `tools/check-directory-readmes [dir]`.

## `validate-helm-values`

`validate-helm-values <manifest.yaml>` renders the chart of every Flux `HelmRelease` in a rendered manifest with
`helm template`, using the values the `HelmRelease` would get on the cluster. It fails when Helm rejects them, for
example because a key is misspelled and the chart's `values.schema.json` doesn't allow it. `test-all-ff validate`
runs it for every Flux `Kustomization`.

The values come from the `HelmRelease`'s `valuesFrom` entries, in order, followed by `spec.values`. Helm merges them
the same way Flux does: maps are merged, and lists and scalars are replaced. The chart comes from the `OCIRepository`
the `HelmRelease` references, or from a `HelmRepository`, and is cached under `${TMPDIR:-/tmp}/gitops-template-charts`.
A semver range is resolved to the newest matching version, as Flux would resolve it.

The `OCIRepository`s and `HelmRelease`s that a Flux Operator `ResourceSet` in the manifest renders are checked too.
Their tag is only known on the cluster, so for an `OCIRepository` whose `spec.ref` is a `<< ... >>` template, the chart
is the newest in the range of the `ResourceSetInputProvider` the `ResourceSet` reads; a fixed tag stays, as
[testdata/resource-set-fixed-tag.yaml](testdata/resource-set-fixed-tag.yaml) checks. The script fails, rather than
guess a version, when the `ResourceSet` doesn't have exactly one `inputsFrom` entry that names a provider in the same
`Kustomization` with a `spec.filter.semver`, such as one that selects its providers by label. `test-all-ff validate`
checks that with [testdata/resource-set-unresolved-version.yaml](testdata/resource-set-unresolved-version.yaml). It
also fails for a `ResourceSet` without a namespace, or one that renders with `spec.resourcesTemplate`, whose objects
it can't render, as [testdata/resource-set-unsupported.yaml](testdata/resource-set-unsupported.yaml) checks. The
provider's namespace, `<< inputs.provider.namespace >>` or `<< inputs.SOURCE.provider.namespace >>` with `Permute`,
is the `ResourceSet`'s own. Rendered objects that still have a `<< ... >>` template in them, such as the ones named
after an entry of the `ResourceSet`'s `spec.inputs`, are left out.

Every ConfigMap and Secret from `valuesFrom` that is in the manifest has to carry the label
`reconcile.fluxcd.io/watch: Enabled`, or the check fails. With the label, helm-controller applies a change to the values
as soon as it's made, not at the `HelmRelease`'s next `interval`.

Some values don't exist until the cluster runs. They are replaced by stubs in [values-stubs](values-stubs/):

- `cluster-values.yaml` replaces the `<cluster>-cluster-values` ConfigMap, which cluster-apps-operator creates for
  each workload cluster.
- `cluster-app-installation-values.yaml` replaces the `cluster-app-installation-values` ConfigMap, which holds the
  management cluster's values, such as `global.managementCluster`. A Kyverno policy copies it into every `org-*`
  namespace of a Giant Swarm management cluster; see the [cluster base](/bases/clusters/capa/readme.md). The
  kind test creates its stand-in from the same file.
- `charts/<chart>.yaml` holds values a chart can't render without the management cluster, such as
  `release-aws`'s switch to render without looking up its Release resource. It is the first values file, so values
  from the repository override it. It doesn't set the region, so that a cluster without one fails.

Because the stub doesn't set a region, a `release-aws` `HelmRelease` without `global.providerSpecific.region` fails
with the chart's own error, "Unable to default the region". On a management cluster, `release-aws` would take the
region of the management cluster's nodes instead, so the cluster would be created where nobody chose. A cluster sets
its region with a component from `bases/environments/regions`, see [Regions](/docs/guides/environments.md#regions).
`test-all-ff validate` checks that the script fails for
[testdata/release-aws-without-region.yaml](testdata/release-aws-without-region.yaml), and for
[testdata/resource-set-cluster-without-region.yaml](testdata/resource-set-cluster-without-region.yaml), where a
`ResourceSet` renders the cluster.

The check leaves out:

- SOPS-encrypted Secrets, because CI has no key to decrypt them.
- Optional `valuesFrom` entries that aren't in the repository.
- `valuesFrom` entries with a `targetPath`. The script prints a note when it skips one.

A `valuesFrom` entry that isn't optional and isn't in the repository fails the check.

A `validate-helm-values.ignore` file next to the script, one `namespace/name` per line, lists `HelmRelease`s whose
errors are known. The repository has none today. The script still renders the listed `HelmRelease`s and prints the
errors, but they don't fail the check. An entry that renders without errors fails the check, so the list can't go stale.

## `fake-flux`

Fake flux is a script that can emulate the behaviour of flux locally before committing your changes to your repository.

Its purpose is to support you in the detection of issues which may arise from syntax errors, failing patches or other
issues caused by incompatibilities with the flux ecosystem.

It builds a Flux `Kustomization` as Flux applies it, not as its file is written. It finds them in the repository's
YAML files outside `tests` and `tools/testdata`: the kind test's assertions in `tests/ats/assertions` name the
repository's `Kustomization`s too, but aren't ones to build.

A `Kustomization` that another Flux `Kustomization` of the repository applies is read from that parent's `flux build`:
in the namespace the parent's `targetNamespace` puts it in, with the values the parent's `postBuild` substitutes. An
organisation's namespace `Kustomization`, `namespace.yaml`, applies its workload clusters' `Kustomization`s this way,
`-direct` ones included, from `../workload-clusters`, with no namespace in their files and
`organization: "${organization}"`. The parent is itself built as Flux applies it, the same way, so the values its own
parent's replacements set reach the child. The parent is the `Kustomization` of this repository, one whose source is
the `GitRepository` of a `Kustomization` that applies the directory its own file is in, such as `MC_NAME.yaml`, whose
build reads the file: `fake-flux` follows the `resources` and `components` of each `kustomization.yaml` from the
parent's path, `../` ones too, and Flux's generated build where there is none. A file that two such builds read fails,
as two `Kustomization`s would apply it. `test-all-ff validate` checks this with the fixture in
[testdata/parent-kustomization](testdata/parent-kustomization).

Without such a parent, as for `MC_NAME.yaml` itself, it builds the directories above the file. Flux's build of a
directory without a `kustomization.yaml` stops at a directory with one and builds that whole, so a replacement there
can change the `Kustomization`: the organisation's `kustomization.yaml` sets `organization` in
`spec.postBuild.substitute`. `fake-flux` builds the file's directory with kustomize if it has a `kustomization.yaml`,
and its parent if that has one too, and so on up, and takes the `Kustomization` from the build of the highest of those
directories that has it. Without one, it reads the file as it is. `test-all-ff validate` checks this with the fixture
in [testdata/ancestor-replacement](testdata/ancestor-replacement).

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
  For example, if the kustomization 'spec.path' is './management-clusters/example/organizations/dev/workload-clusters/dev'
  then 'path' must be a relative path below this, e.g. 'apps/athena'

- `--use-kustomize` Use kustomize to build the kustomization and not 'flux build'

- `yqflags` Optional flags to pass to 'yq'. Use -M to turn off output colouring. See `yq --help` for available flags.
  Does not work with multi-parameter arguments.

- `query` This must be a valid 'yq' query and can be used to filter for specific resources.
           output colouring can be turned off using -M before the query

- `<kustomization>` May be:
  - A number from the list given with `fake-flux list`
  - A name matching a unique kustomization in the set
  - `name:namespace` targeting a specific kustomization in a given namespace

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

- Build all by name and select the athena HelmRelease, whose name ends in -athena

  ```bash
  fake-flux build prod-cluster 'select(.kind == "HelmRelease" and (.metadata.name | test("-athena$")))'
  ```

- Build only the athena app and select its HelmRelease

  ```bash
  fake-flux build 1 apps/athena 'select(.kind == "HelmRelease")'
  ```

- Build only the athena app and select its HelmRelease, turning off output colouring

  ```bash
  fake-flux build 1 apps/athena -M 'select(.kind == "HelmRelease")'
  ```

- Build only the athena app and select its HelmRelease, turning off output colouring. Use kustomize for rendering, not flux

  ```bash
  fake-flux build 1 apps/athena --use-kustomize -M 'select(.kind == "HelmRelease")'
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
