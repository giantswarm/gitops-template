# pushed-password

`management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/pushed-password`

A generated password pushed into the workload cluster through `${cluster_name}-eso-cluster-store`, the `SecretStore`
that the Kyverno policies in the organisation's `multicluster/secret-stores/` make for every cluster. Nothing about
the password is kept in Git.

The cluster's apps Kustomization, `WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml`, applies it into `org-<name>` once the
cluster is up. Until Kyverno and ESO have made the store, ESO retries the push.

## What's here

- `pushed-password.yaml`: a `Password` generator, and a `PushSecret` that writes its password into the Secret
  `pushed-password`, key `password`, in the workload cluster's `default` namespace. `updatePolicy: IfNotExists` keeps
  the first password there: the generator makes a new one at every refresh.

## When you copy it

Change the Secret's name and key to yours. Keep `updatePolicy: IfNotExists`. It needs the organisation's
`multicluster/secret-stores/`, so keep that too.

## Read more

- [Push a generated password](/docs/how-to/workload-cluster-secrets.md#push-a-generated-password)
