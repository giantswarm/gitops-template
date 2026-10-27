# Configuring extra validation and diff previews on GitHub

With this repository, we're also including a GitHub workflow, that can make your work with this
repo easier. It is available in the [validate.yaml](../../.github/workflows/validate.yaml) file. It offers the following
jobs:

- `check_pre_commit`: it runs all the `pre-commit` validation checks,
- `validate`: templates all your `Kustomizations` available in `workload_clusters` and passes the output
  through a YAML and Kubernetes objects linters to make sure that your code is valid YAML and produces final
  manifests understandable to Kubernetes. It attaches a validation report as a comment to your PR.
- `get_diff`: it templates your changed manifests and compares them to a templated version without your changes,
  then it generates and saves a diff between the two and attaches it to your PR
- `test on kind`: deploys a full `flux` installation to a test `kind` cluster, then deploys your `Kustomizations`
  there to verify if they are deployed fine. It checks if all the `Kustomizations` are reconciled as expected
  and additionally if all the statements present in `tests/ats/assertions` are also available in objects in the
  cluster.

You can check a demo PR where this is used in [PR 44](https://github.com/giantswarm/gitops-template/pull/44).

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
in cluster.

### Configuration

This build step requires additional configuration using the following environment variables:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  version provided by Giant Swarm
- `GITOPS_INIT_NAMESPACES`: namespaces used for testing need to be initialized (RBAC permissions) before
  they can be used; as such this variable needs to hold a comma separated list of namespaces, where you want
  to deploy `Kustomization` objects during the test (example: `default,org-org-name`)
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) Flux objects that are expected to have a failed
  state during the test (example - a Kustomization that targets an external cluster:
  "default/clusters-mapi-out-of-band-no-flux-direct")
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. It is recommended
  to set it as a repository secret on github (tho job is configured to pick up this secret by default).
