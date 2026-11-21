# Configure CI in a fork

Your fork comes with GitHub workflows that check every pull request before Flux ever sees it. Most of them work as
they are. This page covers the parts you set yourself: which upstream workflows you follow, the settings and the secret
of the kind test, and when the workflows run. For what each job checks, see [CI checks](../reference/ci-checks.md).

## The workflows

`validate.yaml`, `yaml-diff.yaml` and `validate-file-names.yaml` call shared workflows from
[giantswarm/github-workflows](https://github.com/giantswarm/github-workflows) at a commit SHA, followed by a `# main`
comment, so a change there doesn't change your CI until you take it. With Renovate and the `renovate.json5` this
repository ships, Renovate opens a pull request that moves the SHA to the newest commit on `main` and merges it once
your checks pass. Without Renovate, move the SHA yourself when you want a fix from upstream.

[validate.yaml](../../.github/workflows/validate.yaml) is the one with settings. It passes them to the shared workflow
as inputs, each with a comment that says why it has the value it has:

| Input | Value in this repository |
| --- | --- |
| `python_version` | the Python of `tests/ats/Pipfile` |
| `kubeconform_ver` | the `kubeconform` of `tools/test-all-ff` |
| `kind_ver` | the kind release whose default node image runs the Kubernetes minor version of the management clusters |
| `gitops_flux_app_version` | the `flux-app` chart on the management clusters |
| `gitops_ignored_objects` | empty |
| `gitops_init_namespaces` | `default` |

Renovate keeps the versions up to date through the `# renovate:` comment above each.

## Configuration

The kind test reads these settings, which `validate.yaml` sets through the inputs above and a repository secret:

- `GITOPS_FLUX_APP_VERSION`: the version of [flux-app](https://github.com/giantswarm/flux-app/releases)
  provided by Giant Swarm.
- `GITOPS_INIT_NAMESPACES`: a comma-separated list of the namespaces that exist before Flux applies the repository.
  The test creates the ones that don't exist, and an `automation` ServiceAccount in each, with the rights it has on a
  management cluster: see
  [The rights of the `automation` ServiceAccounts](../reference/ci-checks.md#the-rights-of-the-automation-serviceaccounts).
  [validate.yaml](../../.github/workflows/validate.yaml) sets it to `default` with the `gitops_init_namespaces` input
  of the shared workflow, whose default also names `org-org-name`. The test fails for an `org-*` namespace in the
  list: as on a new management cluster, the organisation's namespace exists only once Flux has applied its
  `Organization`, see
  [The organization-operator stand-in](../reference/ci-checks.md#the-organization-operator-stand-in).
- `GITOPS_IGNORED_OBJECTS`: a comma-separated list of (namespaced) `HelmRelease`s and sources that the test doesn't
  look at (example: "org-org-name/my-helmrelease"). It doesn't apply to `Kustomization`s, which all have to get
  `Ready`. [validate.yaml](../../.github/workflows/validate.yaml) sets it with the `gitops_ignored_objects` input of
  the shared workflow, empty in this repository. Keep it empty: an example the test can reconcile has to get `Ready`,
  so install what it needs in the test instead.
- `GITOPS_MASTER_GPG_KEY`: this variable needs to be a secret (unless you know what you're doing) and needs to contain
  a base64 encoded private master GPG key (armor-encoded, including `-----BEGIN...`
  and `-----END...` header and footer) for your `sops` configuration. Set it as a repository secret on GitHub: the
  job picks up this secret by default. An empty key fails the test, also in a fork's own runs, with one exception: on
  a pull request from a fork, which GitHub gives no secrets, the test skips every test that needs the cluster and
  says so in a warning on the run; the checks that need no cluster still run.

To set the secret from the master key in your keyring, for example with the GitHub CLI:

```sh
gpg --export-secret-keys --armor "${KEY_FP}" | base64 -w0 | gh secret set GITOPS_MASTER_GPG_KEY
```

Only the master key decrypts what the kind test applies: the workload clusters' keys are in the repository, encrypted
with it. Anyone who can change your workflows can read the secret, so treat write access to the repository as access
to the key.

## When the workflows run

`validate.yaml` runs on every pull request, whatever branch it targets, and on every push to `main`. The push run
checks `main` as it is after a merge, which no pull request run has tested when two pull requests merge one after the
other. If your fork's default branch has another name, or you want post-merge runs on more branches, list them under
`on.push.branches`.

A pull request that changes only Markdown files (`*.md`, anywhere in the repository, `CHANGELOG.md` included) skips
`validate` and the kind test, as Markdown changes nothing they check. Its first job, `changes`, lists the files the
pull request changes; a file renamed from or to another type counts as a change to that type too. Instead of the shared
workflow, `validate.yaml` then calls [validate-markdown.yaml](../../.github/workflows/validate-markdown.yaml), which
runs the same `pre-commit` hooks, so the Markdown is still linted, and reports `validate / validate` and
`validate / test_on_kind` as skipped. GitHub counts a skipped check as passed, so a branch that requires these checks
doesn't wait for them. Any other file in the pull request, and every push to `main`, runs everything.

A pull request from a fork gets a read-only token and none of the repository's secrets. `yaml-diff.yaml` and
`validate.yaml` skip their comments there, which they can't post, leave a notice on the run saying why, and put the
diff and the validation log in the job summary. The kind test skips the tests that need
the cluster there; see [`GITOPS_MASTER_GPG_KEY`](#configuration).

The kind test takes a while, so `validate.yaml` runs once per pull request at a time. When you push a new commit to
a pull request, the run for the previous commit is cancelled. Pushes to a branch, such as a merge to `main`, don't
cancel the run in progress: it finishes, and GitHub keeps only the newest of the push runs waiting behind it.
