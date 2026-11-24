# Run the template on another provider

The template's examples create their clusters on AWS, with Cluster API Provider AWS (CAPA). Giant Swarm also runs
clusters on Azure (CAPZ), vSphere (CAPV) and VMware Cloud Director (CAPVCD), and everything in the template but the
cluster itself works there too: the layout, the organisations, the apps, the secrets and the tests. This page lists
what differs for each provider, in the order the [basic tutorial](../tutorials/basic/getting-started.md) meets it, so
you can follow the tutorials on a provider other than AWS.

What it says about the charts was read from the four release charts at v36.2.0. Check the values against the chart of
the release you pick:

```sh
helm show readme oci://gsoci.azurecr.io/charts/giantswarm/release-azure --version RELEASE_VERSION
```

## Contents

- [The provider at a glance](#the-provider-at-a-glance)
- [The cluster base](#the-cluster-base)
- [The release](#the-release)
- [What the cluster's values need](#what-the-clusters-values-need)
- [Regions](#regions)
- [Node pools](#node-pools)
- [The cluster's name](#the-clusters-name)
- [The Gateway's address](#the-gateways-address)
- [DNS and certificates](#dns-and-certificates)
- [Secret stores](#secret-stores)
- [Checks and CI](#checks-and-ci)

## The provider at a glance

| | AWS | Azure | vSphere | Cloud Director |
| --- | --- | --- | --- | --- |
| Short name | `capa` | `capz` | `vsphere` | none |
| Chart | `release-aws` | `release-azure` | `release-vsphere` | `release-cloud-director` |
| Base | `bases/clusters/capa`, in the template | written by `kubectl gs gitops add base` | written by `kubectl gs gitops add base` | written by hand |
| Where the cluster runs | `global.providerSpecific.region` | `global.providerSpecific.location` | the vCenter in `global.providerSpecific.vcenter` | `global.providerSpecific.site`, `org` and `ovdc` |
| Gateway's load balancer | `aws-lb-controller-bundle`, which you install | in the release | in the release, from an address pool you set | in the release |
| external-dns | in the release | in the release | not in the release | not in the release |

## The cluster base

A cluster base holds a provider's chart and the values every cluster on it shares, see
[Share cluster defaults](../tutorials/intermediate/cluster-bases.md). The template ships the CAPA one. For Azure and
vSphere, `kubectl gs gitops add base` writes one, and
[Create a cluster base for another provider](./cluster-base-provider.md) says what to check afterwards:

```sh
kubectl gs gitops add base --provider capz --region westeurope --azure-subscription-id SUBSCRIPTION_ID
kubectl gs gitops add base --provider vsphere
```

`kubectl gs gitops add base` has no Cloud Director provider. Copy `bases/clusters/capa` to a directory of your own,
such as `bases/clusters/cloud-director`, and change two things: the `OCIRepository`'s `url`, to
`oci://gsoci.azurecr.io/charts/giantswarm/release-cloud-director`, and `cluster_config.yaml`, to the values the chart
needs (see [What the cluster's values need](#what-the-clusters-values-need)). The annotations, the labels, the
`HelmRelease` and its `valuesFrom` stay as they are: they're the same for every provider.

Wherever the docs and the examples name `bases/clusters/capa`, name your base instead. Where they run
`kubectl gs template cluster --provider capa`, pass your provider's short name.

## The release

Every provider has its own Giant Swarm releases, and its own chart for them. List the ones your management cluster
knows:

```sh
kubectl get releases.release.giantswarm.io
```

The names start with the provider, such as `aws-`. The `release` variable is the version without that prefix, as it's
the chart's version. Not every release has a chart: `release-aws` has one from v34.0.0 on. For another provider, ask
the registry whether the release you want has one:

```sh
helm show chart oci://gsoci.azurecr.io/charts/giantswarm/release-azure --version RELEASE_VERSION
```

The `# renovate:` comments that keep the release up to date name the chart as their `depName`, such as
`gsoci.azurecr.io/charts/giantswarm/release-aws`. Change it to your provider's chart wherever you copy one, or
Renovate proposes AWS releases for your clusters.

## What the cluster's values need

`cluster_config.yaml` in the base holds what every cluster needs, and a cluster's own `cluster_userconfig.yaml` the
rest, see [Give one cluster its own values](./cluster-values.md). The chart's schema is the authority on what's
required. At v36.2.0:

| Provider | Required by the schema, besides `global.metadata` | You'll also set |
| --- | --- | --- |
| AWS | nothing | `global.providerSpecific.region` |
| Azure | `global.providerSpecific.subscriptionId` | `global.providerSpecific.location` |
| vSphere | nothing | `global.providerSpecific.vcenter` (server, datacenter, datastore, thumbprint, username and password), `global.connectivity.network.controlPlaneEndpoint` and `global.connectivity.network.loadBalancers` |
| Cloud Director | `global.providerSpecific.site`, `org`, `ovdc` and `ovdcNetwork`, and `global.connectivity`, `global.controlPlane` and `global.nodePools` | `global.providerSpecific.userContext.secretRef.secretName`, the Secret with the credentials |

On vSphere and Cloud Director the cluster needs credentials for the infrastructure. They're secrets: don't write them
into `cluster_config.yaml` or `cluster_userconfig.yaml`, which are plain text in Git. Keep them in a Secret in the
organisation's namespace, delivered by [SOPS](./sops.md) or [External Secrets Operator](./external-secrets.md), and
have the cluster read it: on Cloud Director by naming it in `userContext.secretRef.secretName`, on vSphere by adding it
to the `valuesFrom` of the cluster's `HelmRelease`.

`AWSClusterRoleIdentity`, one of the two cluster-scoped kinds the repository may create, exists on CAPA management
clusters only.

## Regions

The template gives every cluster a region, as a kustomize Component from `bases/environments/regions`, see
[Regions](../tutorials/intermediate/stages-and-regions.md#regions). What a region is depends on the provider:

- **AWS.** `global.providerSpecific.region`, such as `eu-central-1`. Without it `release-aws` creates the cluster in
  the management cluster's region, so `tools/test-all-ff validate` fails for a cluster without one.
- **Azure.** `global.providerSpecific.location`, such as `westeurope`. The template's region Components set the AWS
  key, so write your own, as
  [Add a region](./cluster-base-provider.md#add-a-region) shows. `release-azure` renders without a location, so no
  check catches a cluster that has none: list the Component in every cluster.
- **vSphere and Cloud Director.** There's no cloud region. A cluster runs where its vCenter, or its site and virtual
  data centre, are. If all your clusters run in one place, put those values in the base and leave the region
  Components out of your clusters. If you have several, a Component per place is the same idea under another name: one
  directory that sets `global.providerSpecific.vcenter`, or `site` and `ovdc`, for every cluster that lists it.

A region's `node_pool` Component, which adds a pool in the region's availability zones, is AWS too. See
[Node pools](#node-pools).

## Node pools

Every chart has `global.nodePools`, a map of pools by name, and the template's way of layering them holds on every
provider: a base leaves the map out, a Component or the cluster adds pools, and maps are merged, see
[Cluster values](../reference/values.md#cluster-values). What goes into a pool is the provider's:

- **AWS.** `instanceType`, such as `m6i.xlarge`, and `availabilityZones`.
- **Cloud Director.** `sizingPolicy`, `template`, `catalog`, `diskSizeGB`, `placementPolicy` and `storageProfile`,
  with `replicas`.
- **Azure and vSphere.** See the chart's readme for the pool's fields.

So the instance types in the tutorials and the examples, and the zones in the regions' node pools, are AWS's. Swap
them for your provider's sizes. Whether a cluster with no `global.nodePools` gets default pools is the chart's
decision too: `release-aws` gives it some, and `release-cloud-director` requires the map.

## The cluster's name

`release-aws` rejects a cluster name longer than 20 characters, which is where the limit in the tutorials comes from.
The schemas of the other three charts set no limit. Short names are still worth having: the name is the prefix of
every object of the cluster.

## The Gateway's address

Apps in the examples are reached through the Gateway of the
[envoy-gateway](/bases/stacks/envoy-gateway/README.md) stack, and the Gateway needs a load balancer for its Service.
Who provides one differs:

| Provider | What gives the Gateway its address | What you do |
| --- | --- | --- |
| AWS | the AWS Load Balancer Controller, which isn't in a release | Install Giant Swarm's `aws-lb-controller-bundle` on the workload cluster as [its README](https://github.com/giantswarm/aws-lb-controller-bundle#installing) describes, or ask Giant Swarm to |
| Azure | `azure-cloud-controller-manager`, in the release | nothing |
| vSphere | `kube-vip` and `kube-vip-cloud-provider`, in the release | Give the cluster addresses to hand out, in `global.connectivity.network.loadBalancers` |
| Cloud Director | `cloud-provider-cloud-director`, in the release | nothing; `global.connectivity.network.loadBalancers.vipSubnet` sets the subnet |

The stack itself is the same everywhere. Its `gateway-api-config` chart reads the provider from the cluster's values,
and only on AWS asks for a load balancer of a particular kind. So where the docs tell you to install
`aws-lb-controller-bundle`, skip that step on another provider.

**Check:** the Gateway has an address:

```sh
kubectl --context ${WC_CONTEXT} get gateway giantswarm-default -n envoy-gateway-system
```

## DNS and certificates

The Gateway asks for a DNS record for each hostname through a `DNSEndpoint`, and for a certificate from Let's Encrypt
through cert-manager.

- **DNS.** external-dns, which creates the records, is in the AWS and Azure releases. The vSphere and Cloud Director
  releases don't have it, so on those the `DNSEndpoint` is created and nothing acts on it. Create the records yourself,
  pointing at the Gateway's address, or run an external-dns of your own for your DNS provider.
- **Certificates.** cert-manager is in every release. The Gateway's certificate is issued with Let's Encrypt's HTTP01
  challenge, which Let's Encrypt has to reach from the internet. On a network it can't reach, which is common for
  vSphere and Cloud Director, the certificate isn't issued and the page answers with a certificate your browser
  refuses. Use an issuer that works on your network instead.

The cluster's base domain comes from the management cluster's values on every provider.

## Secret stores

[bases/secret_stores](/bases/secret_stores/README.md) has stores for AWS Secrets Manager and Azure Key Vault, which
External Secrets Operator reads with the cloud's workload identity and no stored credential. vSphere and Cloud
Director have no such identity. There a store reads your secret manager, such as Vault, with a credential of its own,
see the end of
[Create a `SecretStore` for your secret manager](./external-secrets.md#create-a-secretstore-for-your-secret-manager).
SOPS works the same on every provider.

## Checks and CI

`tools/test-all-ff validate` renders every cluster's chart with its values, and for that it needs a file of stub
values for the chart, in `tools/values-stubs/charts`, see
[validate-helm-values](../../tools/README.md#validate-helm-values). The template has one for `release-aws`. For
another provider's chart, copy it under the chart's name:

```sh
cp tools/values-stubs/charts/release-aws.yaml tools/values-stubs/charts/release-azure.yaml
```

Its one value, the switch to render without the management cluster's Release resource, is the same in all four
charts. Without the file, the cluster's `HelmRelease` fails the check for a reason that has nothing to do with your
values.

The kind test knows all four charts as cluster charts, so it treats a cluster on any of them as the examples'
clusters: its `HelmRelease` is checked and never installed, see [CI checks](../reference/ci-checks.md). The checks
that fail a cluster without a region are for `release-aws` only.
