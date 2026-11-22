# hello-world-automatic-updates

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world-automatic-updates`

hello-world installed at whatever version is newest in a range, so Flux upgrades it as soon as a matching chart is
published, without a change in Git.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies these objects into `org-<name>`
once the cluster is up. The `HelmRelease` installs into the workload cluster's `hello-world-auto` namespace.

## What's here

- `oci-repository.yaml`: the chart, with `spec.ref.semver: '>=3.2.2 <4.0.0'` instead of a fixed tag: stable releases
  from 3.2.2, the first that accepts the cluster values, up to the next major version.
- `helm-release.yaml`: installs it, once the cluster's Gateway API CRDs are ready.

## When you copy it

Change the chart `url` and the range. Keep the upper bound unless you're happy to get the next major version
unasked. A range takes pre-releases only with a `-0` suffix; on `gsoci.azurecr.io` a pre-release is a build of an
unmerged branch, so leave them to a dev stage, see
[Stages and regions](/docs/tutorials/intermediate/stages-and-regions.md).

## Read more

- [Set a version range](/docs/tutorials/intermediate/automatic-updates.md#set-a-version-range)
