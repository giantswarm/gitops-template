# Read secrets from a secret manager

[External Secrets Operator](https://docs.giantswarm.io/overview/security/external-secrets-operator/) (ESO) copies
secrets from your secret manager, such as Vault, AWS Secrets Manager or Azure Key Vault, into Kubernetes Secrets. The
repository holds only `ExternalSecret`s that say which secret goes where, so no secret value is in Git. ESO runs on
every Giant Swarm management cluster. For when to use it rather than SOPS, or alongside it, see
[Secrets](../explanation/secrets.md).

Export the names the commands use:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export SECRET_STORE=STORE_NAME       # name of the SecretStores in `default` and `org-${ORG_NAME}`
```

## Create a SecretStore for your secret manager

ESO reads a secret manager through a `SecretStore`. A `SecretStore` serves only the `ExternalSecret`s in its own
namespace, so each namespace that reads secrets needs one: the organisation's, `org-${ORG_NAME}`, for its clusters'
apps, and `default` if you read Flux's own secrets there. You can create `SecretStore`s in `default` and the `org-*`
namespaces yourself; a `ClusterSecretStore` is cluster-scoped, which customers can't create.

The bases in [bases/secret_stores](/bases/secret_stores/) give one for each of these, both signing in with a token that
Kubernetes issues for a ServiceAccount, so no cloud credential is stored in the cluster or the repository:

- [azure-key-vault](/bases/secret_stores/azure-key-vault/) reads Azure Key Vault with Azure Workload Identity. In
  Azure, create a managed identity that can read the key vault's secrets, and give it a federated credential for the
  management cluster's service account issuer and the subject
  `system:serviceaccount:org-ORG_NAME:external-secrets-azure-key-vault`, with the audience
  `api://AzureADTokenExchange`, which ESO asks for. Set the key vault's URL in `secret-store.yaml`, and the identity's
  client ID and your tenant ID in `service-account.yaml`.
- [aws-secrets-manager](/bases/secret_stores/aws-secrets-manager/) reads AWS Secrets Manager with IAM roles for
  service accounts. In AWS, create an IAM role that can read your secrets and that trusts the management cluster's
  service account issuer for the subject `system:serviceaccount:org-ORG_NAME:external-secrets-aws-secrets-manager`
  and the audience `sts.amazonaws.com`, which ESO asks for.
  Set the region in `secret-store.yaml` and the role's ARN in `service-account.yaml`.

Ask Giant Swarm support for your management cluster's service account issuer URL.

The bases have no namespace. Use one in your organisation's `namespace` directory, so the store is in the
organisation's namespace next to the clusters' `ExternalSecret`s, for example in
`management-clusters/MC_NAME/organizations/ORG_NAME/namespace/secret-stores/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../../../../bases/secret_stores/azure-key-vault
```

Add `secret-stores` to the `resources` of the organisation's `namespace/kustomization.yaml`: the organisation's
namespace `Kustomization`, `namespace.yaml`, then applies it into the organisation's namespace, see
[Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations).

For the store in `default`, use the base the same way with `namespace: default`, but only once, in the management
cluster's directory rather than an organisation's, so that no two organisations apply the same store. Add that
namespace's subject to the managed identity's federated credentials or the IAM role's trust policy:
`system:serviceaccount:default:external-secrets-azure-key-vault` or
`system:serviceaccount:default:external-secrets-aws-secrets-manager`.

Then point an `ExternalSecret` at the store:

```yaml
spec:
  secretStoreRef:
    kind: SecretStore
    name: azure-key-vault  # or aws-secrets-manager
```

For other secret managers, see
[Using External Secrets Operator](https://docs.giantswarm.io/tutorials/security/external-secrets-operator/) and ESO's
provider docs. Prefer a way to sign in that stores no credential. If your secret manager needs one, it can't come from
ESO, which needs it to read anything: keep it in the repository, encrypted with SOPS, next to the store, see
[Keep secrets in the repository](./sops.md).

**Check:** the stores are `Ready`:

```sh
kubectl get secretstore -n org-${ORG_NAME}
kubectl get secretstore -n default
```

## A secret store for testing

The docs and the examples read secrets through a `SecretStore` in the `default` namespace and one of the same name in
`org-${ORG_NAME}`, both pointing at your secret manager. If you only want to try them and have no store yet, create
them with the [fake provider](https://external-secrets.io/latest/provider/fake/) of External Secrets Operator. It keeps
the values in the store object itself, so it needs no secret manager and no extra credentials.

> [!Caution]
> The token ends up in plain text in the cluster. Use this only for testing, and delete the stores when you're
> done.

Create a store with the values the docs and examples read, first in `default`, then again in `org-${ORG_NAME}` once
the organisation's namespace exists. Put your GitHub token in place of `YOUR_GITHUB_TOKEN`:

```sh
export STORE_NAMESPACE=default  # then org-${ORG_NAME}
cat <<'EOF' | kubectl apply -n "${STORE_NAMESPACE}" -f -
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: gitops-test
spec:
  provider:
    fake:
      data:
        - key: gitops/github-token
          value: YOUR_GITHUB_TOKEN
        - key: gitops/hello-world-values
          value: |
            podAnnotations:
              example.com/source: secret-manager
        - key: workload-clusters-common-token
          value: common-token-from-secret-manager
EOF
```

To try [Report reconcile status on GitHub commits](./commit-statuses.md) too, add its values to the list under
`data`: `gitops/github-commit-status-token`, a GitHub token that can write commit statuses, to both stores, as both
notification directories read it, and `gitops/github-webhook-token`, the secret of the optional webhook, to the store
in `default`.

Check that the store is `Ready`:

```sh
kubectl get secretstore gitops-test -n "${STORE_NAMESPACE}"
```

Then set `SECRET_STORE=gitops-test` and keep the default secret names, `gitops/github-token` and
`gitops/hello-world-values`. The examples in `WC_NAME_OUT_OF_BAND_NO_FLUX_APP` and the `notifications` directories read
this store.

When you're done testing, delete the stores:

```sh
kubectl delete secretstore gitops-test -n default
kubectl delete secretstore gitops-test -n org-${ORG_NAME}
```

## Keep the repository token in your secret manager

Flux reads the repository with the `github-https-credentials` Secret in the `default` namespace. Instead of creating
it by hand or keeping it in the repository encrypted, let ESO write it from your secret manager, through the
`SecretStore` in `default`.

1. Create a GitHub token with read access to the repository's contents, for example a
   [fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token)
   limited to this repository with read-only `Contents` permission. Store it in your secret manager, then save the
   name of that secret:

    ```sh
    export GITHUB_TOKEN_KEY=gitops/github-token
    ```

1. Create an `ExternalSecret`. ESO reads the token and writes it into the `github-https-credentials` Secret, in the
   format Flux expects: GitHub accepts the token as the password of any user name.

    ```sh
    cat <<EOF | kubectl apply -f -
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: github-https-credentials
      namespace: default
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: SecretStore
        name: ${SECRET_STORE}
      target:
        name: github-https-credentials
        template:
          data:
            username: git
            password: "{{ .token }}"
      data:
        - secretKey: token
          remoteRef:
            key: ${GITHUB_TOKEN_KEY}
    EOF
    ```

    If the secret in your secret manager holds several fields, add `property: FIELD_NAME` under `remoteRef`.

1. **Check:** the `ExternalSecret` reports `SecretSynced`:

    ```sh
    kubectl get externalsecret github-https-credentials -n default
    ```

Apply it by hand, as above, before Flux reads the repository for the first time. To keep it in Git from then on, save
the same manifest in `management-clusters/${MC_NAME}`, with `${SECRET_STORE}` and `${GITHUB_TOKEN_KEY}` written out,
and the management cluster's `Kustomization` applies it with the rest. When you rotate the token, change it in your
secret manager: ESO copies it within the `refreshInterval`.

## Give an app secret values

An app reads its secret values from its `${cluster_name}-APP_NAME-user-secrets` Secret, the last layer of its values,
see [App values](../reference/values.md#app-values). An `ExternalSecret` next to the app writes that Secret.

1. Store the values in your secret manager as Helm values in YAML. For the hello-world chart, which has no secret
   settings, this works as an example:

    ```yaml
    podAnnotations:
      example.com/source: secret-manager
    ```

    Save the name of that secret, and the app's name and directory:

    ```sh
    export APP_SECRET_KEY=gitops/hello-world-values
    export APP_NAME=hello-world
    export APP_DIR=management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
    ```

1. Create an `ExternalSecret`. ESO turns the values into the Secret the `HelmRelease` reads. The template's label makes
   Flux upgrade the app as soon as the Secret changes:

    ```sh
    cat <<EOF > ${APP_DIR}/externalsecret.yaml
    apiVersion: external-secrets.io/v1
    kind: ExternalSecret
    metadata:
      name: \${cluster_name}-${APP_NAME}-user-secrets
      namespace: org-\${organization}
    spec:
      refreshInterval: 1h
      secretStoreRef:
        kind: SecretStore
        name: ${SECRET_STORE}
      target:
        name: \${cluster_name}-${APP_NAME}-user-secrets
        template:
          metadata:
            labels:
              reconcile.fluxcd.io/watch: Enabled
      data:
        - secretKey: values
          remoteRef:
            key: ${APP_SECRET_KEY}
    EOF
    ```

1. List it, and push. An app with a `kustomization.yaml` of its own lists it there. An app whose files the cluster's
   `apps/kustomization.yaml` lists one by one, as the `hello-world` example does, gets it listed there, as
   `APP_NAME/externalsecret.yaml`:

    ```sh
    if [ -f ${APP_DIR}/kustomization.yaml ]; then
      yq -i '.resources += ["externalsecret.yaml"]' ${APP_DIR}/kustomization.yaml
    else
      yq -i '.resources += ["'"${APP_NAME}"'/externalsecret.yaml"]' ${APP_DIR}/../kustomization.yaml
    fi
    ```

1. The app's `HelmRelease` has to list the Secret in `valuesFrom`, as the App Templates and
   [Add an app directly](./add-app.md#add-an-app-directly) do:

    ```yaml
    - kind: Secret
      name: ${cluster_name}-hello-world-user-secrets
      optional: true
      valuesKey: values
    ```

**Check:** the `ExternalSecret` reports `SecretSynced`:

```sh
kubectl get externalsecret ${WC_NAME}-${APP_NAME}-user-secrets -n org-${ORG_NAME}
```

For a complete example, see the
[`ExternalSecret` of hello-world](/management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/WC_NAME_OUT_OF_BAND_NO_FLUX_APP/apps/hello-world/externalsecret.yaml)
in the example cluster `WC_NAME_OUT_OF_BAND_NO_FLUX_APP`. It reads the [store for testing](#a-secret-store-for-testing).
The same cluster keeps the secret values of envoy-gateway in a SOPS-encrypted Secret, so it shows both ways side by
side.

## Change a secret value

Change it in your secret manager. ESO copies it into the Secret within the `refreshInterval` of the `ExternalSecret`,
an hour in the examples, and Flux upgrades the release as soon as the Secret changes, as it carries the
`reconcile.fluxcd.io/watch` label. Nothing changes in Git.

To copy it at once rather than wait, ask ESO to refresh the `ExternalSecret`:

```sh
kubectl annotate externalsecret ${WC_NAME}-${APP_NAME}-user-secrets -n org-${ORG_NAME} \
  force-sync=$(date +%s) --overwrite
```
