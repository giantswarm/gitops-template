# WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world-automatic-updates

hello-world installed at whatever version is newest in a range, so Flux upgrades it as soon as a matching chart is
published, without a change in Git.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies these objects into `org-<name>`
once the cluster is up. The `HelmRelease` installs into the workload cluster's `hello-world-auto` namespace.

## What's here

- `oci-repository.yaml`: the chart, with `spec.ref.semver: '>=3.0.0-0'` instead of a fixed tag. The `-0` suffix
  lets pre-releases in.
- `helm-release.yaml`: installs it, once the cluster's Gateway API CRDs are ready.

## When you copy it

Change the chart `url` and the range. Drop the `-0` if you want stable releases only, and cap the range below the
next major version, such as `>=3.0.0 <4.0.0`, if a major version may break you.

## Read more

- [Set a version range](/docs/tutorials/intermediate/automatic-updates.md#set-a-version-range)
