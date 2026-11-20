# Appendices

- [Appendices](#appendices)
  - [Tools](#tools)
    - [Core utilities](#core-utilities)
    - [Working with YAML files](#working-with-yaml-files)
    - [Encryption and Kubernetes tooling](#encryption-and-kubernetes-tooling)
    - [kubectl-gs version](#kubectl-gs-version)
    - [Validating yaml files in the repository](#validating-yaml-files-in-the-repository)
  - [Secret store for testing](#secret-store-for-testing)

## Tools

This section contains the list of tools used throughout the code examples in this repository.

### Core utilities

For core utilities like `base64`, `sed`, `tr`, etc. GNU compatible versions are assumed in the code examples.

### Working with YAML files

For `yq` the [github.com/mikefarah/yq](https://github.com/mikefarah/yq/) version is assumed in the code examples.

### Encryption and Kubernetes tooling

- `gpg` of [GnuPG](https://gnupg.org/) to create and manage the encryption keys
- `sops` of [github.com/getsops/sops](https://github.com/getsops/sops) to encrypt Secrets
- `kubectl` to create manifests and apply the initial configuration to the Management Cluster
- `kubectl gs` of [github.com/giantswarm/kubectl-gs](https://github.com/giantswarm/kubectl-gs) to template
  Giant Swarm resources
- `flux` of [github.com/fluxcd/flux2](https://github.com/fluxcd/flux2) to render and inspect Flux `Kustomizations`

### kubectl-gs version

The `kubectl gs` commands in these docs need kubectl-gs 6.0.0 or newer. Check yours with `kubectl gs --version`, and
update it with `kubectl gs selfupdate`. Older versions lack some of the commands and flags, and an older binary prints
the help text for a command it doesn't know instead of an error, so the command seems to do nothing.

| Command or flag | Added in | Note |
| --- | --- | --- |
| `kubectl gs --version` | 0.6.1 | |
| `kubectl gs login` | 0.5.3 | |
| `kubectl gs login --workload-cluster`, with `--organization` | 1.44.0 | |
| `kubectl gs get clusters`, with `-n` | 0.6.0 | |
| `kubectl gs template organization`, with `--name` | 1.39.0 | |
| `kubectl gs template cluster` printing a Flux `OCIRepository` and `HelmRelease` | 5.13.0 | |
| `kubectl gs gitops add management-cluster`, with `--name`, `--repository-name` and `--gen-master-key` | 2.20.0 | |
| `kubectl gs gitops add management-cluster --skip-encryption` | 5.12.0 | |
| `kubectl gs gitops add organization`, with `--name` and `--management-cluster` | 2.20.0 | |
| `kubectl gs gitops add workload-cluster`, with `--name`, `--organization`, `--management-cluster`, `--repository-name`, `--base` and `--cluster-user-config` | 2.20.0 | Before 6.0.0 it generates the cluster as an App CR, in repository structure version 1. From 6.0.0 it generates structure version 2, with the `mapi` directory. This repository uses structure version 3, without `mapi`, see [Flux Kustomizations](./reference/repo-structure.md#flux-kustomizations) |
| `kubectl gs gitops add workload-cluster --release` | 4.0.0 | Replaced `--cluster-release`. Sets the cluster app version and the `release` since 5.12.0 |
| `kubectl gs gitops add base`, with `--provider` | 2.30.0 | Before 6.0.0 it generates an App CR, in repository structure version 1 |
| `kubectl gs gitops add automatic-update`, with `--management-cluster`, `--organization`, `--workload-cluster` and `--app` | 2.20.0 | Before 6.0.0 it generates Flux image automation instead of a version range on the app's `OCIRepository` |
| `kubectl gs gitops add automatic-update --version-range` | 6.0.0 | |
| `--dry-run` on the `kubectl gs gitops` commands | 2.20.0 | |
| `kubectl gs gitops check`, with `--adopt` | 5.8.0 | Before 6.0.0 it only knows structure version 1. No release knows structure version 3 yet |
| `kubectl gs gitops upgrade` | 5.13.0 | Before 6.0.0 it only knows structure version 1, so there is nothing to upgrade to. No release has the migration to structure version 3 yet |
| `kubectl gs deploy chart`, with `--chart-name`, `--version`, `--organization`, `--target-cluster`, `--target-namespace`, `--values-from` and `--dry-run` | 5.1.0 | `--values-from` with a key and `optional`, as in `ConfigMap/NAME:values`, needs 5.12.0 |
| `kubectl gs selfupdate` | 1.47.0 | |

### Validating yaml files in the repository

You need the following tools installed to use [test-all-ff](/tools/test-all-ff) script.

- `yamllint` of [github.com/adrienverge/yamllint](https://github.com/adrienverge/yamllint)
- `kubeconform` of [github.com/yannh/kubeconform](https://github.com/yannh/kubeconform); CI uses 0.8.0
- `curl`, `sha256sum` and `tar`, to fetch the Flux CRD schemas. See [tools](/tools/README.md#test-all-ff) for the
  schema sources and versions.
- `helm` of [helm.sh](https://helm.sh/docs/intro/install/), to render the chart of every `HelmRelease` with its values

## Secret store for testing

[Getting started](./getting-started.md) reads secrets through a `SecretStore` in the `default` namespace and one of
the same name in `org-${ORG_NAME}`, both pointing at your secret manager. If you only want to try the guide and have
no store yet, create them with the [fake provider](https://external-secrets.io/latest/provider/fake/) of External
Secrets Operator. It keeps the values in the store object itself, so it needs no secret manager and no extra
credentials. You can create `SecretStore`s in `default` and the `org-*` namespaces yourself.

Note that the token ends up in plain text in the cluster. Use this only for testing, and delete the stores when you're
done.

Create a store with the values the guides read, first in `default`, then again in `org-${ORG_NAME}` once
[step 2](./getting-started.md#2-add-an-organization) of the guide has created that namespace. Put your GitHub token in
place of `YOUR_GITHUB_TOKEN`:

```sh
export STORE_NAMESPACE=default  # then org-${ORG_NAME}
cat <<'EOF' | kubectl apply -n "${STORE_NAMESPACE}" -f -
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: gitops-test
spec:
  provider:
    fake:
      data:
        - key: gitops/github-token
          value: YOUR_GITHUB_TOKEN
        - key: gitops/hello-world-values
          value: |
            podAnnotations:
              example.com/source: secret-manager
        - key: workload-clusters-common-token
          value: common-token-from-secret-manager
EOF
```

To try [Report reconcile status on GitHub commits](./guides/commit-statuses.md) too, add its two values to the list
under `data` of the store in `default`: `gitops/github-commit-status-token`, a GitHub token that can write commit
statuses, and `gitops/github-webhook-token`, the secret of the optional webhook.

Check that the store is `Ready`:

```sh
kubectl get secretstore gitops-test -n "${STORE_NAMESPACE}"
```

Then set `SECRET_STORE=gitops-test` in the guide and keep its default secret names, `gitops/github-token` and
`gitops/hello-world-values`.

When you're done testing, delete the stores:

```sh
kubectl delete secretstore gitops-test -n default
kubectl delete secretstore gitops-test -n org-${ORG_NAME}
```
