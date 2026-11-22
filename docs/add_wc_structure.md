# Add a new Workload Cluster repository structure

This page moved to [Create a workload cluster](tutorials/basic/getting-started.md#3-create-a-workload-cluster). The
sections below keep old links working.

## Example

See [the WC_NAME example](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME/).

## Export environment variables

See [Before you start](tutorials/basic/getting-started.md#before-you-start).

## Create Flux GPG regular key pair (optional step)

See [Add a workload cluster key (GPG)](how-to/sops.md#add-a-workload-cluster-key-gpg). If you came here from
`kubectl gs gitops add encryption --help`: on this repository's layout, follow those steps rather than running the
command, which writes the key where the cluster's `Kustomization`s can't read it.

## Create an age key pair (optional step)

See [Add a workload cluster key (age)](how-to/sops.md#add-a-workload-cluster-key-age).

## Directory tree

See [Create a workload cluster](tutorials/basic/getting-started.md#3-create-a-workload-cluster),
[Decrypt a cluster's files](how-to/sops.md#decrypt-a-clusters-files), [App values](reference/values.md#app-values) and
[Add the -direct `Kustomization`](tutorials/advanced/out-of-band.md#add-the--direct-kustomization).

### Configuring default apps

See [Configure the default apps](how-to/cluster-values.md#configure-the-default-apps).

## MC configuration

See [Create a workload cluster](tutorials/basic/getting-started.md#3-create-a-workload-cluster) and
[Add the -direct `Kustomization`](tutorials/advanced/out-of-band.md#add-the--direct-kustomization).

## Recommended next steps

See [Give one cluster its own values](how-to/cluster-values.md) and [the documentation](README.md).
