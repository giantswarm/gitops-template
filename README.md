# GitOps Template

This repository is a template for managing Giant Swarm workload clusters and their apps with GitOps. You describe
clusters and apps as files in Git, and Flux, which runs on every Giant Swarm management cluster, applies them. Copy
it to start your own repository.

Your copy will hold your management cluster's name, your organisations, clusters, regions and node sizes, and your
encrypted secrets, so you'll usually want it private. A GitHub fork of a public repository is always public, so create
a private repository from it with **Use this template** on GitHub instead. On another Git host, clone this repository
and push it to a new private one. To follow the template's changes later, add it as a second remote:
`git remote add template https://github.com/giantswarm/gitops-template.git`. A plain fork is fine for trying the
tutorials with placeholder names, or for contributing back to the template. The docs call your copy "your fork"
either way.

Giant Swarm maintains this template. Its layout has a version, the
[structure version](docs/reference/repo-structure.md#structure-version), and `kubectl gs gitops check`, from
kubectl-gs X.Y.Z on, tells you when your fork has fallen behind it.

## Get started

[Getting started](docs/tutorials/basic/getting-started.md) takes you from a fork of this repository to a workload
cluster with an app. It keeps Flux's own secrets in the repository, encrypted with SOPS, and the app's secret values
in your secret manager, with External Secrets Operator, and says how to use either one on its own.

After that, the tutorials go further in two more tiers:

- **Intermediate:** App Templates, stacks, cluster bases, stages and regions, and automatic updates, starting with
  [App Templates](docs/tutorials/intermediate/app-templates.md).
- **Advanced:** out-of-band resources, scheduled upgrades, multicluster apps, application teams and testing the
  repository, starting with [Out-of-band resources](docs/tutorials/advanced/out-of-band.md).

## Documentation

The [documentation home](docs/README.md) lists every tutorial, how-to guide, reference page and explanation. When
something doesn't get `Ready`, start with [When something isn't Ready](docs/how-to/troubleshooting.md).

## Checking your changes before you push

The repository has an optional [`pre-commit` config](.pre-commit-config.yaml). To use it, see
[Run pre-commit](docs/how-to/check-changes.md#run-pre-commit).

## Contributing

If you work on this template itself, see [CONTRIBUTING.md](CONTRIBUTING.md).
