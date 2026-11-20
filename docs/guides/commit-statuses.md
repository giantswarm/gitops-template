# Report reconcile status on GitHub commits

- [Example](#example)
- [Export environment variables](#export-environment-variables)
- [Commit statuses](#commit-statuses)
  - [Token from your secret manager](#token-from-your-secret-manager)
  - [Token encrypted with SOPS](#token-encrypted-with-sops)
  - [Check the statuses](#check-the-statuses)
- [Fetch on push (optional)](#fetch-on-push-optional)

Flux's notification-controller can tell you on GitHub whether Flux applied a commit. A `Provider` of type `github`
posts a commit status to the repository, and an `Alert` decides which events it gets. With the example's `Alert`s,
every Flux `Kustomization` in the `default` namespace and in the organisation's namespace reports on the commit it
applied: the management cluster's, in `MC_NAME.yaml`, the workload clusters', in the `workload-clusters` directories,
and the `-direct` ones. Each `Kustomization` shows as its own check on the commit, green once it applied the commit and
red when it failed. An event source without a `namespace` matches only the `Alert`'s own namespace, and an `Alert`
reaches only a `Provider` in its own namespace. So the management cluster's `Alert` covers `default`, and each
organisation has its own `Alert`, `Provider` and token in its namespace. Neither covers `flux-giantswarm`, where Giant
Swarm's own `Kustomizations` live, so keep that namespace out of them. The organisation's `Alert` names this
repository's `Kustomization`s in its namespace, the `-direct` ones, instead of `name: "*"`: an application team's
`Kustomization` lives there too, but reads the team's repository, see [Application teams](./app-teams.md). List each
`-direct` `Kustomization` you add.

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

The organisation's are in
[MC_NAME/organizations/ORG_NAME/notifications](/management-clusters/MC_NAME/organizations/ORG_NAME/notifications/):
the same `Provider`, `Alert` and token `ExternalSecret`, in the namespace `org-ORG_NAME`. That's a fixed placeholder:
the organisation's `kustomization.yaml` lists `notifications` and puts the organisation's name into it, see
[The organisation's name](../reference/repo-structure.md#the-organisations-name). Leave it as it is.

The `Kustomization` of the management cluster applies them, so they need no `Kustomization` of their own.

## Export environment variables

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export GITOPS_REPO=REPO_NAME         # name of the Flux GitRepository, for example `gitops`
export GITHUB_REPO=YOUR_ORG/YOUR_REPO
export MC_DIR=management-clusters/${MC_NAME}
export ORG_NAME=ORG_NAME             # organisation whose clusters report, without the `org-` prefix
export ORG_DIR=${MC_DIR}/organizations/${ORG_NAME}
```

## Commit statuses

First, create a GitHub token that can write the repository's commit statuses, for example a
[fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
with read and write access to "Commit statuses". Flux reads it from the `token` key of the
`github-commit-status-token` Secret in the `default` namespace, and in the organisation's. Give it those Secrets in one
of the two ways below, the same way you keep your other secrets.

### Token from your secret manager

External Secrets Operator writes the Secret from your secret manager, as in [Getting started](../getting-started.md).
Store the token in your secret manager, then copy the example:

```sh
mkdir -p ${MC_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-*.yaml ${MC_DIR}/notifications/
cp -r management-clusters/MC_NAME/organizations/ORG_NAME/notifications ${ORG_DIR}/
yq -i '.resources += ["notifications"]' ${ORG_DIR}/kustomization.yaml
```

In both `commit-status-externalsecret.yaml`, set `secretStoreRef` to your store and `remoteRef.key` to the name of the
token in your secret manager. In the organisation's `commit-status-alert.yaml`, name your `-direct` `Kustomization`s. In
both `commit-status-provider.yaml`, set the repository:

```sh
for dir in ${MC_DIR}/notifications ${ORG_DIR}/notifications; do
  yq -i '.spec.address = "https://github.com/'"${GITHUB_REPO}"'"' ${dir}/commit-status-provider.yaml
done
```

### Token encrypted with SOPS

If you keep secrets in the repository, encrypted, as in [Getting started with SOPS](../getting-started-sops.md),
copy the `Provider`s and the `Alert`s only, and name your `-direct` `Kustomization`s in the organisation's `Alert`. The
organisation's `notifications/kustomization.yaml` then lists the encrypted Secret instead of the `ExternalSecret`:

```sh
mkdir -p ${MC_DIR}/notifications ${ORG_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-{provider,alert}.yaml ${MC_DIR}/notifications/
cp management-clusters/MC_NAME/organizations/ORG_NAME/notifications/{kustomization,commit-status-provider,commit-status-alert}.yaml \
  ${ORG_DIR}/notifications/
yq -i '.resources |= map(select(. != "commit-status-externalsecret.yaml")) + ["github-commit-status-token.enc.yaml"]' \
  ${ORG_DIR}/notifications/kustomization.yaml
yq -i '.resources += ["notifications"]' ${ORG_DIR}/kustomization.yaml
for dir in ${MC_DIR}/notifications ${ORG_DIR}/notifications; do
  yq -i '.spec.address = "https://github.com/'"${GITHUB_REPO}"'"' ${dir}/commit-status-provider.yaml
done
```

The Secrets are encrypted with the management cluster's key, the one whose private key is in the `sops-gpg-master`
Secret. Add a rule to `.sops.yaml`, so `sops` encrypts the files in both `notifications` directories with that key.
`KEY_FP` is its fingerprint, as in the management cluster's rule for its `secrets` directory:

```sh
export KEY_FP=MASTER_KEY_FINGERPRINT
yq -i '.creation_rules += [{
  "encrypted_regex": "^(data|stringData)$",
  "path_regex": "management-clusters/'"${MC_NAME}"'/(organizations/[^/]+/)?notifications/.*\\.enc\\.yaml",
  "pgp": "'"${KEY_FP}"'"
}]' .sops.yaml
```

Then write the token into the Secrets, and encrypt them. The organisation's names its real namespace,
`org-${ORG_NAME}`, not the placeholder `org-ORG_NAME`: the organisation's `kustomization.yaml` would change the encrypted
file, which breaks its MAC, so Flux couldn't decrypt it:

```sh
kubectl create secret generic github-commit-status-token --namespace=default \
  --from-literal=token=YOUR_GITHUB_TOKEN --dry-run=client -o yaml \
  > ${MC_DIR}/notifications/github-commit-status-token.enc.yaml
kubectl create secret generic github-commit-status-token --namespace=org-${ORG_NAME} \
  --from-literal=token=YOUR_GITHUB_TOKEN --dry-run=client -o yaml \
  > ${ORG_DIR}/notifications/github-commit-status-token.enc.yaml
sops --encrypt --in-place ${MC_DIR}/notifications/github-commit-status-token.enc.yaml
sops --encrypt --in-place ${ORG_DIR}/notifications/github-commit-status-token.enc.yaml
```

### Check the statuses

Commit and push:

```sh
git add ${MC_DIR}/notifications ${ORG_DIR} && git commit -m "Report reconcile status on commits" && git push
```

The commit after this one shows a check for each `Kustomization` on GitHub, named `kustomization/NAME/...`. If none
shows up, notification-controller logs why, for example a token without access. On a Giant Swarm management cluster,
your Flux runs in the `flux-system` namespace, apart from Giant Swarm's own in `flux-giantswarm`, so read the log of
the notification-controller in `flux-system`:

```sh
kubectl logs -n flux-system deployment/notification-controller | grep github-commit-status
```

If Kustomizations that read another repository live in the same namespaces, list this repository's by name in the
`Alert`s' `eventSources`, instead of `name: "*"`: GitHub refuses statuses for commits it doesn't know.

## Fetch on push (optional)

The `Receiver` needs a secret that GitHub signs its webhook calls with, and GitHub has to reach notification-controller.

1. Create a random secret, for example with `openssl rand -hex 32`. Give it to Flux in the `token` key of the
   `github-webhook-token` Secret in the `default` namespace, the same way as the GitHub token above: copy
   `receiver-externalsecret.yaml` and store the secret in your secret manager, or create and encrypt the Secret with
   SOPS in `${MC_DIR}/notifications/github-webhook-token.enc.yaml`.

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
