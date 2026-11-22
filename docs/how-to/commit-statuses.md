# Report reconcile status on GitHub commits

Flux's notification-controller can tell you on GitHub whether Flux applied a commit. A `Provider` of type `github` posts
a commit status to the repository, and an `Alert` decides which events it gets. Each of this repository's Flux
`Kustomization`s shows as its own check on the commit: green once it applied the commit, red when it failed.

An `Alert` only sees its own namespace (an event source without a `namespace` matches only the `Alert`'s, and an `Alert`
reaches only a `Provider` beside it), so the example has two:

- The management cluster's, in `default`, takes every `Kustomization` there with `name: "*"`: the management cluster's,
  in `MC_NAME.yaml`, and each organisation's namespace `Kustomization`, in `namespace.yaml`.
- Each organisation has its own `Alert`, `Provider` and token in its namespace, for the workload clusters'
  `Kustomization`s in its `workload-clusters` directory. This one names them, instead of `name: "*"`, because an
  application team's `Kustomization` lives in the same namespace but reads the team's repository (see
  [Give an application team its own repository](../tutorials/advanced/teams.md)), and GitHub refuses statuses for
  commits it doesn't know.

> [!Important]
> List each cluster `Kustomization` you add in the organisation's `Alert`. One that isn't listed reports nothing.

Neither `Alert` covers `flux-giantswarm`, where Giant Swarm's own `Kustomization`s live, so keep that namespace out of
them.

A `Receiver` does the opposite: GitHub calls it on a push, and Flux fetches the repository at once instead of
waiting for the `GitRepository`'s interval. It's optional.

Export the names the commands use:

```sh
export MC_NAME=MC_CODENAME           # management cluster codename
export GITOPS_REPO=REPO_NAME         # name of the Flux GitRepository, for example `gitops`
export GITHUB_REPO=YOUR_ORG/YOUR_REPO
export MC_DIR=management-clusters/${MC_NAME}
export ORG_NAME=ORG_NAME             # organisation whose clusters report, without the `org-` prefix
export ORG_DIR=${MC_DIR}/organizations/${ORG_NAME}/namespace   # the organisation's namespace directory
```

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
[MC_NAME/organizations/ORG_NAME/namespace/notifications](/management-clusters/MC_NAME/organizations/ORG_NAME/namespace/notifications/):
the same `Provider`, `Alert` and token `ExternalSecret`, with no namespace. The organisation's
`namespace/kustomization.yaml` lists `notifications`, and its namespace `Kustomization`, `namespace.yaml`, applies them
into the organisation's namespace, see [Flux Kustomizations](../reference/repo-structure.md#flux-kustomizations).

The management cluster's `Kustomization` applies its own, and the organisation's namespace `Kustomization` the
organisation's, so they need no `Kustomization` of their own.

## Commit statuses

First, create a GitHub token that can write the repository's commit statuses, for example a
[fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
with read and write access to "Commit statuses". Flux reads it from the `token` key of the
`github-commit-status-token` Secret in the `default` namespace, and in the organisation's. Give it those Secrets in one
of the two ways below, the same way you keep your other secrets.

## Token from your secret manager

External Secrets Operator writes the Secret from your secret manager, see
[Read secrets from a secret manager](./external-secrets.md). To try it without one, use the
[secret store for testing](./external-secrets.md#a-secret-store-for-testing). Its token is a dummy, so ESO writes the
Secrets but GitHub refuses the statuses: to see them on GitHub, keep a real token
[encrypted with SOPS](#token-encrypted-with-sops) while you test, never in the test store.
Store the token in your secret manager, then copy the example:

```sh
mkdir -p ${MC_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-*.yaml ${MC_DIR}/notifications/
cp -r management-clusters/MC_NAME/organizations/ORG_NAME/namespace/notifications ${ORG_DIR}/
yq -i '.resources += ["notifications"]' ${ORG_DIR}/kustomization.yaml
```

In both `commit-status-externalsecret.yaml`, set `secretStoreRef` to your `SecretStore` in the same namespace,
`default` or `org-${ORG_NAME}`, and `remoteRef.key` to the name of the token in your secret manager. In the
organisation's `commit-status-alert.yaml`, name your cluster `Kustomization`s. In both `commit-status-provider.yaml`,
set the repository:

```sh
for dir in ${MC_DIR}/notifications ${ORG_DIR}/notifications; do
  yq -i '.spec.address = "https://github.com/'"${GITHUB_REPO}"'"' ${dir}/commit-status-provider.yaml
done
```

## Token encrypted with SOPS

If you keep secrets in the repository, encrypted, as in [Keep secrets in the repository](./sops.md),
copy the `Provider`s and the `Alert`s only, and name your cluster `Kustomization`s in the organisation's `Alert`. The
organisation's `notifications/kustomization.yaml` then lists the encrypted Secret instead of the `ExternalSecret`:

```sh
mkdir -p ${MC_DIR}/notifications ${ORG_DIR}/notifications
cp management-clusters/MC_NAME/notifications/commit-status-{provider,alert}.yaml ${MC_DIR}/notifications/
cp management-clusters/MC_NAME/organizations/ORG_NAME/namespace/notifications/{kustomization,commit-status-provider,commit-status-alert}.yaml \
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
  "path_regex": "management-clusters/'"${MC_NAME}"'/(organizations/[^/]+/namespace/)?notifications/.*\\.enc\\.yaml",
  "pgp": "'"${KEY_FP}"'"
}]' .sops.yaml
```

Then write the token into the Secrets. `sops` encrypts each on its way into its file, with the rule above, so the
token never sits in the repository in plain text. It needs the master key's public key in your keyring, which the
first line imports, and `sops` 3.10.0 or newer, see [Tools](../reference/tools.md#tools). The second line reads the
token without it landing in your shell history. The organisation's Secret names its real namespace,
`org-${ORG_NAME}`, the one the organisation's namespace `Kustomization` puts it in, from the start: changing the
encrypted file afterwards would break its MAC, and `sops` couldn't decrypt it to change the token or rotate its key:

```sh
gpg --import ${MC_DIR}/.sops.keys/.sops.master.asc
read -rs GITHUB_TOKEN
kubectl create secret generic github-commit-status-token --namespace=default \
  --from-literal=token="${GITHUB_TOKEN}" --dry-run=client -o yaml |
  sops --encrypt --filename-override ${MC_DIR}/notifications/github-commit-status-token.enc.yaml /dev/stdin \
  > ${MC_DIR}/notifications/github-commit-status-token.enc.yaml
kubectl create secret generic github-commit-status-token --namespace=org-${ORG_NAME} \
  --from-literal=token="${GITHUB_TOKEN}" --dry-run=client -o yaml |
  sops --encrypt --filename-override ${ORG_DIR}/notifications/github-commit-status-token.enc.yaml /dev/stdin \
  > ${ORG_DIR}/notifications/github-commit-status-token.enc.yaml
unset GITHUB_TOKEN
```

## Check the statuses

Commit and push:

```sh
git add ${MC_DIR}/notifications ${ORG_DIR} && git commit -m "Report reconcile status on commits" && git push
```

The commit after this one shows a check for each `Kustomization` on GitHub, named `kustomization/NAME/...`. If none
shows up, notification-controller logs why, for example a token without access. A Giant Swarm management cluster runs
one Flux, in the `flux-giantswarm` namespace, for Giant Swarm and for you. You can't write in that namespace, but you
can read its logs: your read rights cover the whole cluster, pod logs included, and leave out only Secrets and
ConfigMaps.

```sh
kubectl logs -n flux-giantswarm deployment/notification-controller | grep github-commit-status
```

A `Kustomization` that waits for its `dependsOn` shows no check until it has applied the commit or failed. While it
waits, kustomize-controller sends an `info` event for the new commit, and GitHub's `Provider` turns every `info` event
into a green check, so the example's `Alert`s drop that event with their `exclusionList`. If a parent fails on a
commit, the `Kustomization`s waiting on it show no check on that commit at all, rather than a green one.

A green check vouches for the `Kustomization` and nothing further: where it applies a `ResourceSet`, the check says the
`ResourceSet` was applied, not that Flux Operator rendered and applied what it describes, and Flux Operator's own
notifications are switched off on management clusters.

If Kustomizations that read another repository live in the same namespaces, list this repository's by name in the
`Alert`s' `eventSources`, instead of `name: "*"`: GitHub refuses statuses for commits it doesn't know.

## Fetch on push (optional)

> [!Important]
> GitHub has to reach notification-controller, and that takes an object in `flux-giantswarm`, which you can't create.
> Exposing the webhook is Giant Swarm's step. Giant Swarm doesn't expose it on management clusters today, but can be
> asked to: request it for your management cluster before you start, and set up the rest once they've agreed.

The `Receiver` needs a secret that GitHub signs its webhook calls with, and an address GitHub can call.

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

1. Send Giant Swarm that path, for the request you made at the start of this section. They make the `webhook-receiver`
   Service of notification-controller reachable from GitHub for that path only, which needs an `Ingress` or similar
   in `flux-giantswarm`, and tell you the address. You can't do this step yourself.

1. On GitHub, add a webhook to the repository in **Settings** > **Webhooks**: the URL is that address followed by the
   path above, the content type `application/json`, the secret the one from the first step, and the events "Just the
   push event".

GitHub sends a `ping` when you add the webhook, and the webhook shows a green tick once the `Receiver` answered it.
After that, Flux fetches the repository within seconds of every push.
