# Report reconcile status on GitHub commits

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Commit statuses](#commit-statuses)
  - [Token from your secret manager](#token-from-your-secret-manager)
  - [Token encrypted with SOPS](#token-encrypted-with-sops)
  - [Check the statuses](#check-the-statuses)
- [Fetch on push (optional)](#fetch-on-push-optional)

Flux's notification-controller can tell you on GitHub whether Flux applied a commit. A `Provider` of type `github`
posts a commit status to the repository, and an `Alert` decides which events it gets. With the `Alert` below, every
Flux `Kustomization` in the `default` namespace reports on the commit it applied: the management cluster's, in
`MC_NAME.yaml`, and the workload clusters', in the `workload-clusters` directories. Each `Kustomization` shows as its
own check on the commit, green once it applied the commit and red when it failed.

A `Receiver` does the opposite: GitHub calls it on a push, and Flux fetches the repository at once instead of
waiting for the `GitRepository`'s interval. It's optional.

## Example

The example is in [MC_NAME/notifications](/management-clusters/MC_NAME/notifications/):

- [`commit-status-provider.yaml`](/management-clusters/MC_NAME/notifications/commit-status-provider.yaml) and
  [`commit-status-alert.yaml`](/management-clusters/MC_NAME/notifications/commit-status-alert.yaml) post the
  commit statuses,
- [`commit-status-externalsecret.yaml`](/management-clusters/MC_NAME/notifications/commit-status-externalsecret.yaml)
  gives the `Provider` its GitHub token from your secret manager,
- [`receiver.yaml`](/management-clusters/MC_NAME/notifications/receiver.yaml) and
  [`receiver-externalsecret.yaml`](/management-clusters/MC_NAME/notifications/receiver-externalsecret.yaml) are the
  optional `Receiver` and its webhook secret.

The `Kustomization` of the management cluster applies them, so they need no `Kustomization` of their own.

## Export environment variables

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export GITOPS_REPO=REPO_NAME         # name of the Flux GitRepository, for example `gitops`
export GITHUB_REPO=YOUR_ORG/YOUR_REPO
export MC_DIR=management-clusters/${MC_NAME}
```

## Commit statuses

First, create a GitHub token that can write the repository's commit statuses, for example a
[fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
with read and write access to "Commit statuses". Flux reads it from the `token` key of the
`github-commit-status-token` Secret in the `default` namespace. Give it that Secret in one of the two ways below, the
same way you keep your other secrets.

### Token from your secret manager

External Secrets Operator writes the Secret from your secret manager, as in [Getting started](../getting-started.md).
Store the token in your secret manager, then copy the example:

```sh
mkdir -p ${MC_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-*.yaml ${MC_DIR}/notifications/
```

In `commit-status-externalsecret.yaml`, set `secretStoreRef` to your store and `remoteRef.key` to the name of the
token in your secret manager. In `commit-status-provider.yaml`, set the repository:

```sh
yq -i '.spec.address = "https://github.com/'"${GITHUB_REPO}"'"' ${MC_DIR}/notifications/commit-status-provider.yaml
```

### Token encrypted with SOPS

If you keep secrets in the repository, encrypted, as in [Getting started with SOPS](../getting-started-sops.md),
copy the `Provider` and the `Alert` only:

```sh
mkdir -p ${MC_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-{provider,alert}.yaml ${MC_DIR}/notifications/
yq -i '.spec.address = "https://github.com/'"${GITHUB_REPO}"'"' ${MC_DIR}/notifications/commit-status-provider.yaml
```

Then write the token into the Secret, and encrypt it with the management cluster's key, the one whose private key is
in the `sops-gpg-master` Secret. `KEY_FP` is its fingerprint, as in the management cluster's rule in `.sops.yaml`:

```sh
export KEY_FP=MASTER_KEY_FINGERPRINT
kubectl create secret generic github-commit-status-token --namespace=default \
  --from-literal=token=YOUR_GITHUB_TOKEN --dry-run=client -o yaml \
  > ${MC_DIR}/notifications/github-commit-status-token.enc.yaml
sops --encrypt --encrypted-regex '^(data|stringData)$' --pgp "${KEY_FP}" --in-place \
  ${MC_DIR}/notifications/github-commit-status-token.enc.yaml
```

### Check the statuses

Commit and push:

```sh
git add ${MC_DIR}/notifications && git commit -m "Report reconcile status on commits" && git push
```

The commit after this one shows a check for each `Kustomization` on GitHub, named `kustomization/NAME/...`. If none
shows up, notification-controller logs why, for example a token without access. Find the namespace of the
notification-controller that reads the `default` namespace, then read its log:

```sh
kubectl get deployments --all-namespaces -l app.kubernetes.io/component=notification-controller
kubectl logs -n FLUX_NAMESPACE deployment/notification-controller | grep github-commit-status
```

If Kustomizations that read another repository live in the `default` namespace too, list this repository's by name in
the `Alert`'s `eventSources`, instead of `name: "*"`: GitHub refuses statuses for commits it doesn't know.

## Fetch on push (optional)

The `Receiver` needs a secret that GitHub signs its webhook calls with, and GitHub has to reach notification-controller.

1. Create a random secret, for example with `openssl rand -hex 32`. Give it to Flux in the `token` key of the
   `github-webhook-token` Secret in the `default` namespace, the same way as the GitHub token above: copy
   `receiver-externalsecret.yaml` and store the secret in your secret manager, or create and encrypt the Secret with
   SOPS.

1. Copy the `Receiver`, and set the name of your `GitRepository`:

    ```sh
    cp management-clusters/MC_NAME/notifications/receiver.yaml ${MC_DIR}/notifications/
    yq -i '.spec.resources[0].name = "'"${GITOPS_REPO}"'"' ${MC_DIR}/notifications/receiver.yaml
    ```

1. Commit and push. Once the `Receiver` is `Ready`, it shows the path GitHub has to call:

    ```sh
    kubectl get receiver github-push -n default -o jsonpath='{.status.webhookPath}'
    ```

1. Make the `webhook-receiver` Service of notification-controller reachable from GitHub, for example with an
   `Ingress` or `HTTPRoute`, and only for that path. How depends on your management cluster: ask Giant Swarm if
   you're not sure.

1. On GitHub, add a webhook to the repository in **Settings** > **Webhooks**: the URL is your address followed by the
   path above, the content type `application/json`, the secret the one from the first step, and the events "Just the
   push event".

GitHub sends a `ping` when you add the webhook, and the webhook shows a green tick once the `Receiver` answered it.
After that, Flux fetches the repository within seconds of every push.
