# Configuring extra validation and diff previews on GitHub

With this repository, we're also including a GitHub workflow, that can make your work with this
repo easier. It is available in the [validate.yaml](../../.github/workflows/validate.yaml) file.

`validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call shared workflows from
[giantswarm/github-workflows](https://github.com/giantswarm/github-workflows) at a commit SHA, followed by a `# main`
comment, so a change there doesn't change your CI until you take it. With Renovate and the `renovate.json5` this
repository ships, Renovate opens a pull request that moves the SHA to the newest commit on `main` and merges it once
your checks pass. Without Renovate, move the SHA yourself when you want a fix from upstream.

The workflow offers the following jobs:

- `check_pre_commit`: it runs all the `pre-commit` validation checks,
- `validate`: templates all your `Kustomizations` available in `workload_clusters` and passes the output
  through a YAML and Kubernetes objects linters to make sure that your code is valid YAML and produces final
  manifests understandable to Kubernetes. It also renders the chart of every `HelmRelease` with its merged values
  (see [validate-helm-values](../../tools/README.md#validate-helm-values)), so values the chart's schema rejects fail
  the job. It attaches a validation report as a comment to your PR.
- `get_diff`: it templates your changed manifests and compares them to a templated version without your changes,
  then it generates and saves a diff between the two and attaches it to your PR
- `test on kind`: deploys a full `flux` installation to a test `kind` cluster, then deploys your `Kustomizations`
  there to verify if they are deployed fine. It checks if all the `Kustomizations` are reconciled as expected
  and additionally if all the statements present in `tests/ats/assertions` are also available in objects in the
  cluster.

You can check a demo PR where this is used in [PR 44](https://github.com/giantswarm/gitops-template/pull/44).

## When the workflow runs

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

## `test-on-kind` validation step - additional information

This validation step offers some broader possibilities for validation, but also requires extra configuration.

### Validation option

By default, this test checks if all the `Kustomization` objects except the ones defined in `GITOPS_IGNORED_OBJECTS`
environment variable are successfully reconciled in the cluster.

Additionally, every file present in `tests/ats/assertions/exists` is loaded and verified. Each of these files
has to contain one or more YAML description of objects of Kubernetes objects you expect to be present in the cluster
after your Kustomizations are deployed. Each object has to have `kind:`, `metadata.name` and `metadata.namespace`
(if it's a namespace-scoped object) defined. The rest of object definition is arbitrary, but every property specified
in the assertions file must be also present (and have exactly the same value) as the property of the object present
in cluster. Strings are compared as text, so a ConfigMap's `values` has to match line by line. Only trailing whitespace
is ignored: whether the assertion writes a block as `|` or `|-`, or a line ends in a space, doesn't matter.

### Versions

The test cluster runs the same versions as a Giant Swarm management cluster where it can:

| Component | Version | Set in |
| --- | --- | --- |
| Kubernetes | v1.36.1, the default node image of kind v0.32.0 | `kind_ver` in [validate.yaml](../../.github/workflows/validate.yaml) |
| flux-app | 1.12.2 (Flux v2.7.5) | `gitops_flux_app_version` in validate.yaml |
| app-operator and chart-operator | installed by apptestctl 0.27.0 | `apptestctl_ver` in validate.yaml |
| Cluster API CRDs | v1.14.4 | `CAPI_VERSION` in [conftest.py](../../tests/ats/conftest.py) |

The shared workflow doesn't take a node image, so the Kubernetes patch version is whatever the kind release defaults
to. pytest prints the version it ran against at the top of its output, as `kubernetes server: v1.36.1 (linux/amd64)`.

### Cluster API

This repository doesn't test cluster creation. Workload clusters are created by the `release-aws` chart on a real
management cluster, which a kind cluster can't stand in for.

The test cluster has the Cluster API core CRDs only: the `CustomResourceDefinition`s from the `core-components.yaml`
of the Cluster API release, in the `cluster.x-k8s.io` group and its `addons`, `ipam` and `runtime` subgroups. It runs no
Cluster API controllers and no infrastructure providers such as CAPA or CAPZ, so nothing acts on a Cluster API object.
A test can create one, for example a stand-in `Cluster`, and set its status itself. Use `v1beta2`, the version the
objects are stored in: the CRDs are installed without their conversion webhook, so other versions are served without
conversion.

The shared workflow still installs `clusterctl`, at its own default version, but nothing uses it.

### Configuration

This build step requires additional configuration using the following environment variables:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  version provided by Giant Swarm
- `GITOPS_INIT_NAMESPACES`: namespaces used for testing need to be initialized (RBAC permissions) before
  they can be used; as such this variable needs to hold a comma separated list of namespaces, where you want
  to deploy `Kustomization` objects during the test (example: `default,org-org-name`)
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) Flux objects that are expected to have a failed
  state during the test (example: "org-org-name/my-kustomization"). [validate.yaml](../../.github/workflows/validate.yaml)
  sets it with the `gitops_ignored_objects` input of the shared workflow, empty in this repository. Update it there
  when you add a `Kustomization` that can't become ready in the test cluster.
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. It is recommended
  to set it as a repository secret on github (tho job is configured to pick up this secret by default).

### The workload cluster of the `-direct` out-of-band example

`WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml` applies its manifests straight to a workload cluster, through the
`mapi-out-of-band-no-flux-kubeconfig` Secret a management cluster has for it. The test installs a
[vCluster](https://www.vcluster.com/) named `mapi-out-of-band-no-flux` in the test cluster and puts its kubeconfig, with
the vCluster's in-cluster Service as the server, in that Secret, so the `Kustomization` reconciles like on a management
cluster. Every file in `tests/ats/assertions/exists-in-workload-cluster` is verified against the vCluster, the same way
as the files in `tests/ats/assertions/exists`. Running the test locally needs `helm` in your `$PATH`.

## Superseded runs

The kind test takes a while, so `validate.yaml` runs once per pull request at a time. When you push a new commit to
a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
cancel the run in progress: it finishes, and GitHub keeps only the newest of the push runs waiting behind it.
