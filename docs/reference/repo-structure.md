# Repository structure

- [Layout](#layout)
- [Structure version](#structure-version)
- [Naming](#naming)
- [Optional components](#optional-components)
  - [`[OTHER_RESOURCES]`](#other_resources)
  - [`[kustomization.yaml]`](#kustomizationyaml)
  - [`[organizations]` and `[workload-clusters]`](#organizations-and-workload-clusters)
  - [`mapi` and `[out-of-band]`](#mapi-and-out-of-band)
- [Flux Kustomizations](#flux-kustomizations)

This page lists the directories and files of the repository and the rules for them. For how Flux turns them into
clusters, see [How it works](../how-it-works.md).

## Layout

The repository follows the hierarchy of the platform: a management cluster has organizations, and an organization
has workload clusters.

```text
.sops.yaml
bases
├── app_sets
├── apps
├── cluster_templates
├── clusters
└── environments
management-clusters
└── MC_NAME
    ├── .sops.keys
    ├── [kustomization.yaml]
    ├── [OTHER_RESOURCES]
    ├── secrets
    |   ├── MC_NAME.gpgkey.enc.yaml
    |   ├── [WC_NAME.gpgkey.enc.yaml]
    |   └── [WC_NAME-direct.gpgkey.enc.yaml]
    ├── MC_NAME.yaml
    └── [organizations]
        ├── [kustomization.yaml]
        └── ORG_NAME
            ├── [kustomization.yaml]                    (mandatory when there are no workload-clusters)
            ├── [OTHER_RESOURCES]
            ├── ORG_NAME.yaml
            └── [workload-clusters]
                ├── kustomization.yaml
                ├── WC_NAME.yaml
                ├── [WC_NAME-direct.yaml]
                └── WC_NAME                             managed from MC_NAME.yaml
-----------------------------------------------------------------------------------
                    ├── [out-of-band]                     WC_NAME.yaml responsibility
                    |   ├── [kustomization.yaml]
                    |   └── [OTHER_RESOURCES]
                    └── mapi
                        ├── [kustomization.yaml]
                        ├── apps
                        ├── cluster
                        └── [OTHER_RESOURCES]
```

How to read it:

- Names in capital letters are placeholders. Replace them with your own names, following the [naming](#naming) rules.
- Names with an extension, like `MC_NAME.yaml`, are files. The rest are directories.
- Names in square brackets are optional. See [optional components](#optional-components).
- The horizontal line splits the work between the two [Flux Kustomizations](#flux-kustomizations). `MC_NAME.yaml`
  applies everything above it, and `WC_NAME.yaml` applies everything below it.
- `.sops.yaml`, `.sops.keys` and the `*.gpgkey.enc.yaml` files are only needed when you encrypt secrets with SOPS.
  See [SOPS keys](./sops-keys.md).

## Structure version

The structure on this page has a version, so a repository built on it can tell when it has fallen behind. The
current structure version is `1`. It goes up when an existing repository has to change to follow the structure, for
example when a directory moves or a naming rule changes. New examples and changes to the apps under `bases/` don't
change it.

`kubectl gs gitops` records the version in a `.gitops-metadata.yaml` file at the root of the repository, with an
entry for every management cluster, organization, workload cluster, app and base it created:

```yaml
apiVersion: gitops.giantswarm.io/v1alpha1
kind: RepositoryMetadata
structureVersion: 1
generatedWith: kubectl-gs/5.7.3
layers:
  - kind: management-cluster
    path: management-clusters/MC_NAME
    structureVersion: 1
    generatedWith: kubectl-gs/5.7.3
```

The file sits outside of what Flux applies, so it never reaches a cluster. Don't edit it by hand.

To see which parts of your repository are behind, run this in your clone:

```sh
kubectl gs gitops check
```

It exits with an error when anything is behind, so you can run it in CI. If your repository is older than the
metadata file, run `kubectl gs gitops check --adopt` once to record what's there as current.

To bring the repository up to date, first see which files would change:

```sh
kubectl gs gitops upgrade --dry-run
```

Then run the upgrade:

```sh
kubectl gs gitops upgrade
```

It changes the files in place and keeps your own edits where it can. Review the result with `git diff` before you
commit it. If something goes wrong, undo it with Git. That's why the command doesn't run on a repository with
uncommitted changes unless you pass `--force`.

Note that layers recorded without a structure version can't be upgraded. If you know the version they were created
with, set their `structureVersion` by hand. Otherwise, remove their entries and run
`kubectl gs gitops check --adopt`.

If your `kubectl-gs` doesn't have the `check` and `upgrade` commands, update it with `kubectl gs selfupdate`.

## Naming

| Placeholder | Rule |
| --- | --- |
| `MC_NAME` | The management cluster's codename |
| `ORG_NAME` | The organization's name, in lowercase and without the `org-` prefix |
| `WC_NAME` | Any name, but the workload cluster's name is clearest |

## Optional components

### `[OTHER_RESOURCES]`

These are any other Kubernetes resources you add, as files or directories, at the level they belong to. When you
have more than a few, group them by kind:

```text
management-clusters
└── demomc
    ├── secrets
    |   ├── secret-1.enc.yaml
    |   └── secret-2.enc.yaml
    └── configmaps
        └── cm.yaml
```

### `[kustomization.yaml]`

If a directory has no `kustomization.yaml`, Flux generates one that includes every file in it and in its
subdirectories, until it finds a `kustomization.yaml`. Add one when you want to list the resources yourself or use
other [kustomize features](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/#kustomize-feature-list).

If you add one, include this option. It records in every resource the file it came from, which makes debugging
easier:

```yaml
buildMetadata: [originAnnotations]
```

### `[organizations]` and `[workload-clusters]`

These directories keep the organizations apart from the management cluster's other resources, and the workload
clusters apart from the organization's other resources. Use them when there are other resources at the same level:

```text
management-clusters
└── demomc
    ├── secrets
    |   └── mc-secret-1.enc.yaml
    └── organizations
        └── demo-gitops
            ├── demo-gitops.yaml
            ├── secrets
            |   └── org-secret-1.enc.yaml
            └── workload-clusters
                ├── kustomization.yaml
                ├── demo0.yaml
                └── demo0
```

Don't mix organizations, or workload clusters, with other resources in one directory. If there are no other
resources, you can leave the directory out and put the organizations or clusters right under their parent:

```text
management-clusters
└── demomc
    └── demo-gitops
        ├── demo-gitops.yaml
        ├── kustomization.yaml
        ├── demo0.yaml
        └── demo0
```

### `mapi` and `[out-of-band]`

Every workload cluster directory has a `mapi` directory. It holds the resources on the management cluster that
configure the workload cluster, through the Management API. Examples are the cluster App, the apps' `HelmRelease`
and `OCIRepository` resources, and the ConfigMaps and Secrets with their values.

The optional `out-of-band` directory holds resources that go straight into the workload cluster, such as extra
ConfigMaps, Secrets or Deployments that aren't delivered as an app. There are two ways to apply it:

- Run Flux in the workload cluster and point it at the `out-of-band` directory.
- Add another Flux Kustomization on the management cluster that uses the workload cluster's kubeconfig.

## Flux Kustomizations

Two kinds of Flux Kustomization apply the repository:

```text
management-clusters
└── MC_NAME
    ├── MC_NAME.yaml                        # applies MC_NAME/, up to WC_NAME.yaml
    └── organizations
        └── ORG_NAME
            └── workload-clusters
                ├── kustomization.yaml
                ├── WC_NAME.yaml            # applies WC_NAME/
                └── WC_NAME
                    └── mapi
                        ├── apps
                        └── cluster
```

`MC_NAME.yaml` applies everything in `MC_NAME/` but stops at the workload clusters. The `kustomization.yaml` in
`workload-clusters` lists only the cluster Kustomizations, so Flux creates those and not the cluster directories:

```yaml
resources:
  - WC_NAME.yaml
```

`WC_NAME.yaml` then applies its `WC_NAME/` directory. It also sets the variables, like `${cluster_name}`, that the
bases use. See [How it works](../how-it-works.md) for why there are two.
