# aws-secrets-manager

`bases/secret_stores/aws-secrets-manager`

A `SecretStore` named `aws-secrets-manager` that reads AWS Secrets Manager with IAM roles for service accounts. External
Secrets Operator assumes the IAM role the ServiceAccount names, with a token Kubernetes issues for that ServiceAccount,
so no access key is stored anywhere.

Nothing applies this directory directly. A `kustomization.yaml` in your organisation's `namespace/` lists it, and the
Flux `Kustomization` for the organisation's namespace applies it into `org-<name>`.

## What's here

- `secret-store.yaml`: the `SecretStore`, with the region of your secrets.
- `service-account.yaml`: the ServiceAccount `external-secrets-aws-secrets-manager`, annotated with the IAM role.
- `kustomization.yaml`: lists both.

## When you copy it

You don't copy it, you list it. Set the region in `secret-store.yaml` and the role's ARN in `service-account.yaml`. In
AWS, create an IAM role that can read your secrets and trusts the management cluster's service account issuer for the
subject `system:serviceaccount:org-<name>:external-secrets-aws-secrets-manager` and the audience `sts.amazonaws.com`.
Giant Swarm support can give you the issuer URL. Keep the ServiceAccount's name, or change the subject to match.

## Read more

- [Create a SecretStore](/docs/how-to/external-secrets.md#create-a-secretstore-for-your-secret-manager)
- [Use your secret manager](/docs/how-to/workload-cluster-secrets.md#use-your-secret-manager)
