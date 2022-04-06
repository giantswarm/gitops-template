# GitOps Template

This repository presents structure, ideas and best practices for managing clusters and apps
using Flux available by default on Giant Swarm Management Clusters.

*Warning:* This repository is of a preview quality right now and still a work in progress.
Please bear in mind that it might have some elements that are not strictly needed or left
loose after we ported some ideas from other repositories.

## Using this repository

A good starting point is the
[repository structure](docs/repo_structure.md) doc, which explains how this repository
works.

To start creating and managing your infrastructure using this template, please
fork a repo from it, then follow the docs below to learn how it works:

1. [add a new Management Cluster](./docs/add_mc.md)
1. [add a new Organization](./docs/add_org.md)
1. [add a new Workload Cluster](./docs/add_wc.md)
1. [add a new App to a Workload Cluster](./docs/add_appcr.md)
1. [update an existing App](./docs/update_appcr.md)
1. [enable automatic updates of an existing App](./docs/automatic_updates_appcr.md)

## Contributing

To ensure your YAML and Markdown formatting is OK even before you push to the repository,
we have prepared [`pre-commit` config](.pre-commit-config.yaml). To use it, make sure to:

- [install](https://pre-commit.com/#install) `pre-commit`
- when contributing to the repo for the first time, run `pre-commit install --install-hooks`

Remember:

- `pre-commit` is optional and opt-in: you have to set it up yourself.
- To check your code without doing git commit, you can run `pre-commit run -a`
- To force a git commit without running `pre-commit` hook, run `git commit --no-verify ...`
