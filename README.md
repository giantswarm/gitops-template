# GitOps Template

This repository presents structure, ideas and best practices for managing clusters and apps
using Flux available by default on Giant Swarm Management Clusters.

*Warning:* This repository is of a preview quality right now and still a work in progress.
Please bear in mind that it might have some elements that are not strictly needed or left
loose after we ported some ideas from other repositories.
Work in progress and new features are tracked [in this ticket](https://github.com/giantswarm/giantswarm/issues/21243).

## Using this repository

A good starting point is the
[repository structure](docs/repo_structure.md) doc, which explains how this repository
works.

Please check [Appendices](docs/appendices.md) on the assumptions made for the code examples throughout this repository.

To start creating and managing your infrastructure using this template, please
fork a repo from it, then follow the docs below to learn how it works:

1. [add a new Management Cluster](./docs/add_mc.md)
1. [add a new Organization](./docs/add_org.md)
1. [add a new Workload Cluster](./docs/add_wc.md)
   1. [create a template for mass instantiation of clusters](docs/add_wc_template.md)
   1. create a cluster instance using a template
      1. [create the necessary GitOps repo structure](./docs/add_wc_structure.md)
      1. [create a cluster infrastructure](./docs/add_wc_instance.md)
1. [manage applications deployed to a cluster](./docs/apps/README.md)

## Configuring extra validation and diff previews on GitHub

With this repository, we're also including a GitHub workflow, that can make your work with this
repo easier. It is available in the [validate.yaml](.github/workflows/validate.yaml) file. It offers the following
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

### `test-on-kind` validation step - additional information

This validation step offers some broader possibilities for validation, but also requires extra configuration.

#### Validation option

By default, this test checks if all the `Kustomization` objects except the ones defined in `GITOPS_IGNORED_OBJECTS`
environment variable are successfully reconciled in the cluster.

Additionally, every file present in `tests/ats/assertions/exists` is loaded and verified. Each of these files
has to contain one or more YAML description of objects of Kubernetes objects you expect to be present in the cluster
after your Kustomizations are deployed. Each object has to have `kind:`, `metadata.name` and `metadata.namespace`
(if it's a namespace-scoped object) defined. The rest of object definition is arbitrary, but every property specified
in the assertions file must be also present (and have exactly the same value) as the property of the object present
in cluster.

#### Configuration

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

## Contributing

To ensure your YAML and Markdown formatting is OK even before you push to the repository,
we have prepared [`pre-commit` config](.pre-commit-config.yaml). To use it, make sure to:

- [install](https://pre-commit.com/#install) `pre-commit`
- when contributing to the repo for the first time, run `pre-commit install --install-hooks`

Remember:

- `pre-commit` is optional and opt-in: you have to set it up yourself.
- To check your code without doing git commit, you can run `pre-commit run -a`
- To force a git commit without running `pre-commit` hook, run `git commit --no-verify ...`
