# Documentation

The documentation comes in four kinds, each for a different moment. Tutorials teach you by building something, step
by step. How-to guides get one job done, for when you already know your way round. Reference pages are for looking
things up. Explanations say why the repository is built the way it is.

If you're new here, start with the [basic tutorial](./tutorials/basic/getting-started.md).

## Tutorials

The tutorials are routes through the same repository, in three tiers. Each one builds on the one before.

### Basic

- [Getting started](./tutorials/basic/getting-started.md): from a management cluster to an organisation, a workload
  cluster and an app, with SOPS for the bootstrap secrets and External Secrets Operator for the app's secrets.

### Intermediate

- [App Templates](./tutorials/intermediate/app-templates.md): reuse an app's configuration across clusters.
- [Stacks](./tutorials/intermediate/stacks.md): deploy several apps together.
- [Cluster bases](./tutorials/intermediate/cluster-bases.md): share cluster defaults through a base.
- [Stages and regions](./tutorials/intermediate/stages-and-regions.md): run dev, staging and production clusters in
  several regions.
- [Automatic updates](./tutorials/intermediate/automatic-updates.md): let Flux install new chart versions.

### Advanced

- [Out-of-band resources](./tutorials/advanced/out-of-band.md): apply resources straight to a workload cluster, pushed
  from the management cluster or pulled by the workload cluster's own Flux.
- [Scheduled upgrades](./tutorials/advanced/scheduled-upgrades.md): hold app and release upgrades until an upgrade
  window, with `ResourceSet`s.
- [Multicluster apps](./tutorials/advanced/multicluster-apps.md): roll one app out to many clusters of an
  organisation.
- [Application teams](./tutorials/advanced/teams.md): give an application team its own repository.
- [Testing the repository](./tutorials/advanced/testing.md): test the repository on kind and with Chainsaw.

## How-to guides

- [When something isn't Ready](./how-to/troubleshooting.md): what a red status means, and how to recover.
- [Add an app](./how-to/add-app.md) to one cluster.
- [Change an app](./how-to/update-app.md): its version, how it's installed, or its values.
- [Adopt an app that's already installed](./how-to/adopt-app.md), by hand or through an `App`, without
  installing it again.
- [Give one cluster its own values](./how-to/cluster-values.md).
- [Keep secrets in the repository](./how-to/sops.md) with SOPS.
- [Read secrets from a secret manager with External Secrets Operator](./how-to/external-secrets.md).
- [Put secrets into new workload clusters](./how-to/workload-cluster-secrets.md).
- [Give every organisation the same object](./how-to/share-objects.md).
- [Delete a workload cluster](./how-to/delete-cluster.md) and everything it uses.
- [Let kubectl-gs write the files](./how-to/kubectl-gs.md), and what to fix afterwards.
- [Create a cluster base for another provider](./how-to/cluster-base-provider.md), other than CAPA.
- [Move a running cluster to scheduled upgrades](./how-to/scheduled-upgrades-existing-cluster.md) without changing it.
- [Report reconcile status on GitHub commits](./how-to/commit-statuses.md).
- [Bring an older fork up to date](./how-to/upgrade-fork.md).
- [Check a change before you push](./how-to/check-changes.md).
- [Configure CI in a fork](./how-to/configure-ci.md).

## Reference

- [Repository structure](./reference/repo-structure.md): every directory and file, and the rules for them.
- [SOPS keys](./reference/sops-keys.md): which key decrypts what.
- [Values](./reference/values.md): the `valuesFrom` layers of clusters and apps, in order.
- [Tools and versions](./reference/tools.md): the tools the docs use, and the kubectl-gs version each command needs.
- [CI checks](./reference/ci-checks.md): what each CI job and test checks.

## Explanation

- [How it works](./explanation/how-it-works.md): what happens between a push and a running cluster.
- [Secrets](./explanation/secrets.md): SOPS and External Secrets Operator in one repository, and which secret goes
  where.
- [Deletion protection](./explanation/deletion-protection.md): what keeps clusters, organisations and keys from being
  deleted.
- [One owner per object](./explanation/one-owner.md): why two tools, or one tool told twice, must never reconcile the
  same object, and how to tell when they do.
- [Composition](./explanation/composition.md): why environments are directories, and when to use a base, a Component
  or a stack.
