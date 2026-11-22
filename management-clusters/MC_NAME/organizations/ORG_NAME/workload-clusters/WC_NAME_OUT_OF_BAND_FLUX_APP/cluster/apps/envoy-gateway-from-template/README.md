# envoy-gateway-from-template

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_FLUX_APP/cluster/apps/envoy-gateway-from-template`

The [`envoy-gateway`](/bases/stacks/envoy-gateway/) stack as base apps of this cluster, with the cluster's own
values on top. Base apps install with the cluster, so the Gateway is there before the secondary apps that route
through it.

The cluster's Flux `Kustomization`, `WC_NAME_OUT_OF_BAND_FLUX_APP.yaml`, applies it into `org-<name>` together with the
cluster, through `cluster/apps/kustomization.yaml`.

## What's here

- `kustomization.yaml`: lists the stack, turns the values below into the
  `${cluster_name}-gateway-api-config-user-values` ConfigMap, and labels the encrypted Secret so a change reaches
  the `HelmRelease` at once.
- `user_config_gateway_api_config.yaml`: the Gateway's `hello` subdomain, for hello-world, and an example
  annotation.
- `secret.enc.yaml`: more values for `gateway-api-config`, in the `${cluster_name}-gateway-api-config-user-secrets`
  Secret, encrypted with SOPS and the cluster's GPG key.

## When you copy it

Put your subdomains and overrides in the values file. Write your own `secret.enc.yaml` and encrypt it with your
cluster's key, or delete it and its line in `kustomization.yaml`: a copy encrypted for another cluster won't
decrypt.

## Read more

- [Use it in a cluster](/docs/tutorials/intermediate/stacks.md#use-it-in-a-cluster)
- [Encrypt an app's values](/docs/how-to/sops.md#encrypt-an-apps-values)
