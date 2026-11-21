# GitOps Template

This repository is a template for managing Giant Swarm workload clusters and their apps with GitOps. You describe
clusters and apps as files in Git, and Flux, which runs on every Giant Swarm management cluster, applies them. Fork
it to start your own repository.

Giant Swarm maintains this template. Its layout has a version, the
[structure version](docs/reference/repo-structure.md#structure-version), and `kubectl gs gitops check` tells you when
your fork has fallen behind it.

## Get started

[Getting started](docs/tutorials/basic/getting-started.md) takes you from a fork of this repository to a workload
cluster with an app. It keeps Flux's own secrets in the repository, encrypted with SOPS, and the app's secret values
in your secret manager, with External Secrets Operator, and says how to use either one on its own.

After that, the tutorials go further in two more tiers:

- **Intermediate:** App Templates, stacks, cluster bases, stages and regions, and automatic updates, starting with
  [App Templates](docs/tutorials/intermediate/app-templates.md).
- **Advanced:** out-of-band resources, scheduled upgrades, multicluster apps, application teams and testing the
  repository, starting with [Out-of-band resources](docs/tutorials/advanced/out-of-band.md).

## Guides

The [documentation home](docs/README.md) lists every tutorial, how-to guide, reference page and explanation.

## Reference

- [Repository structure](docs/reference/repo-structure.md) lists every directory and file, and the rules for them.
- [SOPS keys](docs/reference/sops-keys.md) explains which key decrypts which files.
- [Values](docs/reference/values.md) lists the `valuesFrom` layers of clusters and apps, in order.
- [Tools](docs/reference/tools.md) lists the tools the docs use, and the kubectl-gs version each command needs.
- [CI checks](docs/reference/ci-checks.md) explains what each CI job and test checks.

## Checking your changes before you push

The repository has an optional [`pre-commit` config](.pre-commit-config.yaml): see
[Run pre-commit](docs/how-to/check-changes.md#run-pre-commit).

## Contributing

If you work on this template itself, see [CONTRIBUTING.md](CONTRIBUTING.md).
