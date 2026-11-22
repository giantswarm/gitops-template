# workload-cluster-secrets

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/workload-cluster-secrets`

Secrets pushed into the workload cluster as soon as it's up, through a store you keep in Git: one secret every cluster
needs, from your secret manager, and one password generated for this cluster alone.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies these objects into
`org-<name>` once the cluster is up. External Secrets Operator on the management cluster then writes the Secrets into
the workload cluster's `default` namespace.

## What's here

- `secret-store.yaml`: the workload cluster as a `SecretStore`, `${cluster_name}-workload-cluster`, reached through
  the cluster's kubeconfig Secret.
- `common-secret.yaml`: an `ExternalSecret` that reads `workload-clusters-common-token` from your secret manager, and
  a `PushSecret` that copies it into the cluster as `common-secret`.
- `generated-password.yaml`: a `Password` generator, an `ExternalSecret` that keeps the first password it makes, and a
  `PushSecret` that copies it into the cluster as `generated-password`, once.

## When you copy it

Point the `ExternalSecret` in `common-secret.yaml` at your own store, such as one from `bases/secret_stores`, and at
your secret's name. Keep `refreshPolicy: CreatedOnce` and `updatePolicy: IfNotExists` on the password, or it changes
at every refresh. To give every cluster a store without writing one per cluster, use the Kyverno policy instead, as
[`pushed-password`](../pushed-password/) does.

## Read more

- [Push secrets through a store in Git](/docs/how-to/workload-cluster-secrets.md#push-secrets-through-a-store-in-git)
- [Use your secret manager](/docs/how-to/workload-cluster-secrets.md#use-your-secret-manager)
