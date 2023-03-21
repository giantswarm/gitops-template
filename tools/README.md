# Tools

## `test-all-fb`

You can use this bash tool under a repository based on this template to verify the syntax of your manifests.

## `fake-flux`

Fake flux is a script that can emulate the behaviour of flux locally before committing your changes to your repository.

It's purpose is to support you in the detection of issues which may arise from syntax errors, failing patches or other
issues caused by incompatibilities with the flux ecosystem.

For a detailed description of what this tool can do, please see `fake-flux usage` which includes a comprehensive set of
examples.

### Requirements

- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [yq](https://github.com/mikefarah/yq)
- [fake-flux](https://github.com/giantswarm/gitops-template/blob/main/tools/fake-flux)

### Usage

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
  fak-flux build 1 apps/athena 'select(.kind == "App")'
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
