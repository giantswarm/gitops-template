# GitOps Template

This repository is a template for managing Giant Swarm workload clusters and their apps with GitOps. You describe
clusters and apps as files in Git, and Flux, which runs on every Giant Swarm management cluster, applies them. Fork
it to start your own repository.

*Warning:* This repository is of a preview quality right now and still a work in progress.
Please bear in mind that it might have some elements that are not strictly needed or left
loose after we ported some ideas from other repositories.
Work in progress and new features are tracked [in this ticket](https://github.com/giantswarm/giantswarm/issues/21243).

## Get started

[Getting started](docs/getting-started.md) takes you from a fork of this repository to a workload cluster with an
app. It keeps secrets in a secret manager with External Secrets Operator. If you'd rather keep secrets in the
repository, encrypted with SOPS, follow [Getting started with SOPS](docs/getting-started-sops.md) instead.

To learn what happens between a `git push` and a running cluster, read [How it works](docs/how-it-works.md).

## Guides

The [guides](docs/guides/README.md) cover what comes after getting started, such as cluster templates, environments
for dev, staging and production, and adding and updating apps.

These pages explain each part of the repository step by step:

- [Add a management cluster](docs/add_mc.md)
- [Add an organization](docs/add_org.md)
- [Add a workload cluster](docs/add_wc.md)

## Reference

- [Repository structure](docs/reference/repo-structure.md) lists every directory and file, and the rules for them.
- [SOPS keys](docs/reference/sops-keys.md) explains which key decrypts which files.
- [Appendices](docs/appendices.md) lists the tools the examples use.
- [Validation and diff previews on GitHub](docs/guides/ci-validation.md) explains the workflow that checks your
  changes.

## Checking your changes before you push

The repository has a [`pre-commit` config](.pre-commit-config.yaml) that checks the YAML and Markdown formatting
before each commit. It's optional. To use it, [install](https://pre-commit.com/#install) `pre-commit`, then set up
the hooks once in your clone:

```sh
pre-commit install --install-hooks
```

To run the checks without committing:

```sh
pre-commit run -a
```

To commit without running them, use `git commit --no-verify`.

## Contributing

If you work on this template itself, see [CONTRIBUTING.md](CONTRIBUTING.md).
