# Tools

This directory holds the scripts that check the repository: `test-all-ff` and the scripts it runs, and the checks
pre-commit runs.

## Requirements

The scripts here need some of these tools:

- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [yq](https://github.com/mikefarah/yq)
- [yamllint](https://github.com/adrienverge/yamllint)
- [kubeconform](https://github.com/yannh/kubeconform); CI uses 0.8.0
- `curl`, `sha256sum` and `tar`, to fetch the Flux CRD schemas
- [flux](https://fluxcd.io/flux/installation/#install-the-flux-cli), for `fake-flux` on its own: `test-all-ff` brings its
  own, see below
- [kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/binaries/)
- [helm](https://helm.sh/docs/intro/install/), for `validate-helm-values`

## Provides

This directory provides these scripts:

- [test-all-ff](test-all-ff)
- [fake-flux](fake-flux)
- [validate-helm-values](validate-helm-values)
- [check-directory-readmes](check-directory-readmes)
- [check-sops-encrypted](check-sops-encrypted)

## `test-all-ff`

`test-all-ff` is a bash script that checks the syntax of the manifests in a repository based on this template. It runs
them through `yamllint`, `kubeconform` and `validate-helm-values`, so that what passes all the checks is likely to
apply on the cluster.

It runs `fake-flux` for each Flux `Kustomization` it finds that applies this repository: one whose source is the
source of `MC_NAME.yaml`, the `Kustomization` that applies the directory its file is in, as in
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

`fake-flux` builds with the Flux CLI of the same version, whatever `flux` you have installed: `test-all-ff` downloads
the `v2.7.5` release archive for Linux or macOS on amd64 or arm64 once and keeps it under
`${TMPDIR:-/tmp}/gitops-template-schemas`. Every run checks the archive's SHA-256 against the one at the top of the
script, unpacks the CLI into the run's own temporary directory and puts it first in the `PATH` it runs `fake-flux`
with, so a cached CLI is never run unchecked. A cached archive that doesn't match fails the run: delete it to download
it again. `validate` checks that the CLI is that version, and that a changed archive is refused. When you move
`FLUX_VERSION`, move the CLI checksums and `FLUX_CRD_SCHEMAS_SHA256` with it, from the release's
`flux_<version>_checksums.txt` and `crd-schemas.tar.gz`.

### test-all-ff usage

- `validate` tests every Flux `Kustomization` it finds with `yamllint`, `kubeconform` and `validate-helm-values`.
  - It also builds each base in `bases/secret_stores` with `kubectl kustomize` and checks it with `kubeconform`. They
    read cloud secret managers, so no cluster in the repository uses them and no `Kustomization` builds them.
  - It checks the manifests of every `out-of-band` directory that no `Kustomization` applies with `kubeconform` too.
    A workload cluster's own Flux pulls such a directory, so nothing else in the repository builds it. A directory
    with a `kustomization.yaml` is built with `kubectl kustomize` first, and a SOPS-encrypted Secret is checked
    without its `sops` key.
- `template` prints the manifest of the whole repository.

## `check-directory-readmes`

Every directory of the template's examples, which a customer reads, copies or edits, explains itself with a README.
`check-directory-readmes` makes sure of it: it walks the directories of the files git tracks, staged files included,
and fails for a directory without a tracked `README.md` (or `readme.md`). It checks only the template's own examples:

- the bases the template ships, listed in `SHIPPED` at the top of the script;
- `management-clusters/` itself, and the placeholder management cluster `management-clusters/MC_NAME/` and everything
  below it, which holds the example organisation `ORG_NAME/` and the example clusters.

A customer's own directories aren't checked: a fork's management cluster, its organisations and clusters, and a base
it adds, such as `bases/clusters/my-defaults/`, need no README, so a fork that follows the tutorials passes. `tests/`,
`tools/`, `.github/` and `docs/` are left out, and so is a directory git doesn't know about yet, until you stage a file
in it. pre-commit runs it, so CI does too, also on a pull request that changes only Markdown. It runs with bash 3.2, as
on macOS.

Some leaves are copies of one shape, such as the stages, the regions or an example cluster's `cluster/` and `apps/`.
One README in the parent covers them, and the `COVERED` list at the top of the script names each one with its parent.
The check fails for an entry whose directory is gone while its parent is still there, and for a parent README that
doesn't name a leaf it covers in backticks, as its path relative to the parent followed by a slash, such as
`` `dev/` ``. A longer path doesn't count: `` `apps/cert-manager/` `` doesn't name `apps/`.

When you add a directory to the template's examples, give it a README. If it's a base, also list it in `SHIPPED`, or the
check skips it. If it's another copy of a shape a parent README already describes, list it in `COVERED` and name it in
that README instead.

An entry whose parent is gone too went with its example, so a fork that deletes `management-clusters/MC_NAME` passes.
`test-all-ff validate` checks that the script fails in each of those cases, and passes for a customer's own directories
and in a fork without the examples. Those cases change the examples, so a fork that deleted them skips them, and says
so.

### check-directory-readmes usage

Run it from the root of a git repository, or pass the root as the only argument: `tools/check-directory-readmes [dir]`.

## `check-sops-encrypted`

A file named `*.enc.yaml` is meant to be encrypted with SOPS, and one that isn't puts its secret in Git for good: Git
keeps history, and a master key in plain text gives away every other key in the repository. `check-sops-encrypted` is
a seatbelt for that. It fails for a `*.enc.yaml` file git tracks, staged files included, that has a YAML document
without a top-level `sops` key, the one `sops` adds to every document it encrypts. An empty file fails too. It checks
the copy in the working tree and the staged copy, so it also catches a file you staged in plain text and encrypted
afterwards without staging it again.

A file git doesn't know about yet isn't checked until you stage it, so a file you've only just written doesn't stop
you committing something else. The documented procedures never write one in plain text anyway: they pipe the Secret
straight into `sops --encrypt`, see [Keep secrets in the repository](/docs/how-to/sops.md). pre-commit runs the check,
so CI does too, also on a pull request that changes only Markdown. It runs with bash 3.2, as on macOS, and needs only
`git` and `awk`.

It checks the file's name and the key, not the encryption itself: a file that names `sops` at the top level by hand
passes. It doesn't look at files with other names, so keep the `.enc.yaml` ending for everything you encrypt, as the
`.sops.yaml` rules expect anyway.

`test-all-ff validate` checks that the script fails in each of those cases, and passes for a file git doesn't track.

### check-sops-encrypted usage

Run it from the root of a git repository, or pass the root as the only argument: `tools/check-sops-encrypted [dir]`.

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
after an entry of the `ResourceSet`'s `spec.inputs`, are left out, and the script names each one it leaves out, as
`ResourceSet <namespace>/<name>: <kind> <name> left out`. Only the kind test checks them.

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
  from the repository override it. It doesn't set the region, so that a cluster without one fails. The template has
  one for `release-aws`; a fork with clusters on another provider adds one for that chart, see
  [Checks and CI](/docs/how-to/other-providers.md#checks-and-ci).

Because the stub doesn't set a region, a `release-aws` `HelmRelease` without `global.providerSpecific.region` fails
with the chart's own error, "Unable to default the region". On a management cluster, `release-aws` would take the
region of the management cluster's nodes instead, so the cluster would be created where nobody chose. A cluster sets
its region with a component from `bases/environments/regions`, see [Regions](/docs/tutorials/intermediate/stages-and-regions.md#regions).
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

`fake-flux` emulates what Flux does, locally, so you can check your changes before you commit them. It catches syntax
errors, failing patches and other incompatibilities with Flux.

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

For a full description of what the script can do, with examples, run `fake-flux usage`.

### fake-flux usage

- `list` lists every Flux `Kustomization` in the current repository.
- `build <kustomization> [path] [--use-kustomize] [yqflags] [query]` builds the given `Kustomization` and optionally
  filters it for specific resources.

#### Arguments

> The arguments must come in the order shown. The script fails if they don't.

- `<kustomization>` May be:
  - A number: the index `fake-flux list` gives the `Kustomization`.
  - A name, unique in the repository.
  - `name:namespace`, to pick the `Kustomization` of that name in that namespace. Separate the two with a single `:`.

#### Optional arguments

- `path` is a path below the `spec.path` of the `Kustomization` you build. For example, if its `spec.path` is
  `./management-clusters/example/organizations/dev/workload-clusters/dev`, `path` is a relative path below it, such as
  `apps/athena`.

- `--use-kustomize` builds the `Kustomization` with kustomize instead of `flux build`.

- `yqflags` are flags to pass to `yq`. `-M` turns off output colouring; `yq --help` lists the others. Flags that take
  several parameters don't work.

- `query` is a `yq` query that filters for specific resources. Put `-M` before it to turn off output colouring.

- `<kustomization>` May be:
  - A number from the list `fake-flux list` gives.
  - A name that matches one `Kustomization` only.
  - `name:namespace`, to pick the `Kustomization` of that name in that namespace.

### Examples

- Build every resource of a `Kustomization`, by its index

  ```bash
  fake-flux build 1
  ```

- Build every resource of a `Kustomization`, by its name

  ```bash
  fake-flux build prod-cluster
  ```

- Build the `Kustomization` `prod` in the `org-example` namespace

  ```bash
  fake-flux build prod:org-example
  ```

- Build by index, but only the `apps/athena` path below it

  ```bash
  fake-flux build 1 apps/athena
  ```

- Build by name and select the athena `HelmRelease`, whose name ends in `-athena`

  ```bash
  fake-flux build prod-cluster 'select(.kind == "HelmRelease" and (.metadata.name | test("-athena$")))'
  ```

- Build only the athena app and select its `HelmRelease`

  ```bash
  fake-flux build 1 apps/athena 'select(.kind == "HelmRelease")'
  ```

- Build only the athena app and select its `HelmRelease`, with output colouring turned off

  ```bash
  fake-flux build 1 apps/athena -M 'select(.kind == "HelmRelease")'
  ```

- Build only the athena app and select its `HelmRelease`, with output colouring turned off, rendering with kustomize
  instead of Flux

  ```bash
  fake-flux build 1 apps/athena --use-kustomize -M 'select(.kind == "HelmRelease")'
  ```

### Caveats

- The script can't carry out replacements that come from Secrets or ConfigMaps.
- In its default mode, which uses `flux build kustomization`, the script replaces a Secret's data with the type of
  encryption used for it. To see the whole encrypted Secret, add `--use-kustomize`, which builds with `kustomize`
  instead of `flux`.
- Neither the script nor the tools it runs decrypt Secrets, even when you have the keys locally. To see the output with
  decrypted Secrets, decrypt them first.

### Examples of the differences in behaviour between flux and kustomize for secrets

With `flux build`, a Secret in the output looks like this:

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

Decoded, the value is:

```nohighlight
**SOPS**
```

With `kustomize` as the build engine, the Secret is longer and holds the encrypted values:

```yaml
apiVersion: v1
data:
  values: ENC[AES256_GCM,data:<<<ENCRYPTED_MESSAGE>>>,tag:TAG_VALUE,type:str]
kind: Secret
metadata:
  annotations:
    config.kubernetes.io/origin: |
      path: encrypted-secret.enc.yaml
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
